"""Small, loopback-only MCP Streamable HTTP transport (Python 3.9+).

This module never calls a model or an external account. Business authorization,
PDF approval and account isolation belong to the supplied service. The transport
uses stateless JSON replies, not SSE or the deprecated HTTP+SSE protocol.

Protocol references (verified 2026-10-24):
https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle
https://docs.rag.bailian.aliyun.com/cookbook/office-agent
"""

import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


SUPPORTED_VERSIONS = ("2025-03-26", "2025-06-18", "2025-11-25")
CURRENT_VERSION = SUPPORTED_VERSIONS[-1]
MAX_BODY_BYTES = 2 * 1024 * 1024
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ConnectorError(Exception):
    """A service error whose short message may be shown to the user."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _reject_constant(value):
    raise ValueError("Non-finite JSON number")


def _pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            raise ValueError("Duplicate JSON member")
        result[key] = value
    return result


def make_handler(service, base_url):
    """Return a BaseHTTPRequestHandler bound to a loopback service.

    Required service methods:
      authenticate(bearer_token) -> principal, or raise ConnectorError
      list_tools() -> list of MCP Tool schemas
      call_tool(principal, name, arguments) -> JSON-serializable business result

    Optional methods:
      read_resource(principal, uri) -> MCP ReadResourceResult
      handle_http(method, path, headers, body) ->
          (status, content_type, bytes, extra_headers), or None

    The UI service must use its own browser session/CSRF checks. A model token is
    never interpreted as a browser confirmation by this transport.
    """
    parsed = urlsplit(base_url)
    try:
        port = parsed.port if parsed.port is not None else 80
    except ValueError:
        raise ValueError("base_url must be a loopback HTTP origin")
    if (parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/") or not 1 <= port <= 65535):
        raise ValueError("base_url must be a loopback HTTP origin")

    class Handler(BaseHTTPRequestHandler):
        server_version = "OfferPathLocal/1"
        sys_version = ""

        def log_message(self, *_args):
            # Paths, request bodies and Authorization headers are never logged.
            pass

        def send_error(self, code, message=None, explain=None):
            # Also cover unsupported HTTP verbs and parser errors consistently.
            self._http_error(code, "HTTP request rejected")

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def _send(self, status, kind="application/json; charset=utf-8", body=b"",
                  headers=None):
            if not isinstance(body, bytes):
                raise TypeError("HTTP body must be bytes")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; "
                             "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                             "object-src 'self'; frame-ancestors 'none'; "
                             "base-uri 'none'; form-action 'self'")
            self.send_header("Referrer-Policy", "no-referrer")
            for name, value in (headers or {}).items():
                # The service may set cookies/ETags, but cannot weaken the guard.
                if name.lower() not in {
                    "content-length", "content-type", "cache-control",
                    "content-security-policy", "x-content-type-options",
                    "referrer-policy", "access-control-allow-origin",
                    "access-control-allow-credentials", "transfer-encoding",
                } and "\r" not in str(value) and "\n" not in str(value):
                    self.send_header(name, str(value))
            self.end_headers()
            if body and self.command != "HEAD":
                self.wfile.write(body)

        def _http_error(self, status, message, headers=None):
            self.close_connection = True
            self._send(status, body=_json_bytes({"error": message}), headers=headers)

        def _rpc_error(self, request_id, code, message, status=200):
            self._send(status, body=_json_bytes({"jsonrpc": "2.0", "id": request_id,
                                                "error": {"code": code, "message": message}}))

        def _rpc_result(self, request_id, result):
            try:
                body = _json_bytes({"jsonrpc": "2.0", "id": request_id,
                                    "result": result})
            except (TypeError, ValueError, OverflowError, RecursionError):
                return self._rpc_error(request_id, -32603, "Internal error")
            self._send(200, body=body)

        def _guard(self, require_origin=False):
            hosts = self.headers.get_all("Host", [])
            origins = self.headers.get_all("Origin", [])
            if len(hosts) != 1 or len(origins) > 1:
                self._http_error(403, "Invalid local host or origin")
                return False
            host = hosts[0]
            try:
                value = urlsplit("http://" + host)
                valid = (value.hostname in LOOPBACK_HOSTS and value.port == port
                         and not value.username and not value.password
                         and not value.path and not value.query and not value.fragment)
            except ValueError:
                valid = False
            if not valid:
                self._http_error(403, "Local host and port required")
                return False
            if require_origin and not origins:
                self._http_error(403, "Same-origin browser request required")
                return False
            if origins:
                try:
                    origin = urlsplit(origins[0])
                    valid = (origin.scheme == "http" and origin.hostname == value.hostname
                             and origin.port == port and not origin.username
                             and not origin.password and not origin.path
                             and not origin.query and not origin.fragment)
                except ValueError:
                    valid = False
                if not valid:
                    self._http_error(403, "Cross-origin request rejected")
                    return False
            return True

        def _body(self):
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
                raise ConnectorError(400, "A single Content-Length is required")
            if not re.fullmatch(r"[0-9]+", lengths[0]):
                raise ConnectorError(400, "Invalid Content-Length")
            size = int(lengths[0])
            if size > MAX_BODY_BYTES:
                raise ConnectorError(413, "Request body is too large")
            try:
                raw = self.rfile.read(size)
            except (TimeoutError, OSError):
                raise ConnectorError(408, "Request body timed out")
            if len(raw) != size:
                raise ConnectorError(400, "Incomplete request body")
            return raw

        def _authenticate(self):
            values = self.headers.get_all("Authorization", [])
            if len(values) != 1 or not values[0].startswith("Bearer "):
                raise ConnectorError(401, "A connection token is required")
            bearer = values[0][7:]
            if not bearer or any(ch.isspace() for ch in bearer):
                raise ConnectorError(401, "Invalid connection token")
            self._bearer = bearer
            principal = service.authenticate(bearer)
            if principal is None:
                raise ConnectorError(401, "Invalid connection token")
            return principal

        def _safe_error(self, error, fallback="Unable to complete this request"):
            # Unexpected exceptions are never exposed. ConnectorError and service
            # errors with an explicit HTTP status may carry a user-facing message.
            if isinstance(error, ConnectorError) or isinstance(getattr(error, "status", None), int):
                message = str(getattr(error, "message", None) or str(error))[:500]
                bearer = getattr(self, "_bearer", "")
                if bearer:
                    message = message.replace(bearer, "[redacted]")
                message = re.sub(r"(?i)bearer\s+[^\s,;]+", "Bearer [redacted]", message)
                return message or fallback
            return fallback

        def _service_http(self, body=b""):
            fn = getattr(service, "handle_http", None)
            if not callable(fn):
                return self._http_error(404, "Not found")
            try:
                result = fn(self.command, self.path, self.headers, body)
                if result is None:
                    return self._http_error(404, "Not found")
                status, kind, content, extra = result
                self._send(status, kind, content, extra)
            except Exception as error:
                status = getattr(error, "status", 500)
                if not isinstance(status, int) or not 400 <= status <= 599:
                    status = 500
                self._http_error(status, self._safe_error(error))

        def do_GET(self):
            if not self._guard():
                return
            if urlsplit(self.path).path == "/mcp":
                return self._http_error(405, "SSE is not offered", {"Allow": "POST, DELETE"})
            self._service_http()

        def do_HEAD(self):
            if not self._guard():
                return
            self._http_error(405, "Method not allowed", {"Allow": "GET, POST"})

        def do_OPTIONS(self):
            if not self._guard():
                return
            self._http_error(405, "Cross-origin access is not offered", {"Allow": "GET, POST, DELETE"})

        def do_DELETE(self):
            if not self._guard():
                return
            if urlsplit(self.path).path != "/mcp":
                return self._http_error(405, "Method not allowed")
            try:
                self._authenticate()
            except Exception as error:
                return self._http_error(401, self._safe_error(error, "Invalid connection token"),
                                        {"WWW-Authenticate": "Bearer"})
            self._send(204)

        def do_POST(self):
            is_mcp = urlsplit(self.path).path == "/mcp"
            if not self._guard(require_origin=not is_mcp):
                return
            try:
                principal = self._authenticate() if is_mcp else None
                raw = self._body()
            except Exception as error:
                status = getattr(error, "status", 500)
                if not isinstance(status, int) or not 400 <= status <= 599:
                    status = 500
                return self._http_error(status, self._safe_error(error),
                                        {"WWW-Authenticate": "Bearer"} if status == 401 else None)
            if not is_mcp:
                return self._service_http(raw)
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                return self._http_error(415, "application/json is required")
            version = self.headers.get("MCP-Protocol-Version")
            if version and version not in SUPPORTED_VERSIONS:
                return self._http_error(400, "Unsupported MCP protocol version")
            try:
                message = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant,
                                     object_pairs_hook=_pairs)
            except (UnicodeDecodeError, ValueError, RecursionError):
                return self._rpc_error(None, -32700, "Parse error", 400)
            if not isinstance(message, dict):
                return self._rpc_error(None, -32600, "Single JSON-RPC request required", 400)
            request_id = message.get("id")
            valid_id = isinstance(request_id, (str, int)) and not isinstance(request_id, bool)
            if (message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str)
                    or not message["method"] or ("id" in message and not valid_id)):
                return self._rpc_error(None, -32600, "Invalid Request", 400)
            method = message["method"]
            params = message.get("params", {})
            if not isinstance(params, dict):
                return self._rpc_error(request_id, -32602, "Invalid params", 400)
            if "id" not in message:
                if method in ("notifications/initialized", "notifications/cancelled",
                              "notifications/progress"):
                    return self._send(202)
                return self._rpc_error(None, -32601, "Method not found", 400)
            if method == "initialize":
                wanted = params.get("protocolVersion")
                if (not isinstance(wanted, str) or not isinstance(params.get("capabilities"), dict)
                        or not isinstance(params.get("clientInfo"), dict)):
                    return self._rpc_error(request_id, -32602, "Invalid initialize params")
                negotiated = wanted if wanted in SUPPORTED_VERSIONS else CURRENT_VERSION
                capabilities = {"tools": {"listChanged": False}}
                if callable(getattr(service, "read_resource", None)):
                    capabilities["resources"] = {"subscribe": False, "listChanged": False}
                return self._rpc_result(request_id, {
                    "protocolVersion": negotiated, "capabilities": capabilities,
                    "serverInfo": {"name": "offerpath-job-agent", "version": "0.1.0"},
                    "instructions": "Local synthetic connector. Human PDF confirmation is required; "
                                    "tool access never authorizes an application submission.",
                })
            if method == "ping":
                return self._rpc_result(request_id, {})
            if method == "tools/list":
                try:
                    return self._rpc_result(request_id, {"tools": service.list_tools()})
                except Exception:
                    return self._rpc_error(request_id, -32603, "Unable to list tools")
            if method == "tools/call":
                name, arguments = params.get("name"), params.get("arguments", {})
                if not isinstance(name, str) or not name or not isinstance(arguments, dict):
                    return self._rpc_error(request_id, -32602, "Invalid tool params")
                try:
                    result = service.call_tool(principal, name, arguments)
                    text = _json_bytes(result).decode("utf-8")
                    answer = {"content": [{"type": "text", "text": text}], "isError": False}
                    if isinstance(result, dict) and version != "2025-03-26":
                        answer["structuredContent"] = result
                    return self._rpc_result(request_id, answer)
                except Exception as error:
                    return self._rpc_result(request_id, {"content": [{"type": "text",
                        "text": self._safe_error(error)}], "isError": True})
            if method == "resources/read" and callable(getattr(service, "read_resource", None)):
                if not isinstance(params.get("uri"), str) or not params["uri"]:
                    return self._rpc_error(request_id, -32602, "Invalid resource params")
                try:
                    return self._rpc_result(request_id, service.read_resource(principal, params["uri"]))
                except Exception as error:
                    return self._rpc_error(request_id, -32002, self._safe_error(error))
            if method == "resources/list" and callable(getattr(service, "read_resource", None)):
                return self._rpc_result(request_id, {"resources": []})
            return self._rpc_error(request_id, -32601, "Method not found")

    return Handler
