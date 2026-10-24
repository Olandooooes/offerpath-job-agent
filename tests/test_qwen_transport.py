"""Synthetic wire-level checks; no client account or model API is used."""

import contextlib
import http.client
import importlib.util
import io
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "qwen_transport", Path(__file__).parents[1] / "scripts/qwen_transport.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class FakeService:
    def __init__(self):
        self.calls = []
        self.ui_calls = []

    def authenticate(self, bearer):
        if bearer != "synthetic-connection-only":
            raise m.ConnectorError(401, "Invalid connection token")
        return "synthetic-user"

    def list_tools(self):
        return [{"name": "save_draft", "description": "Save synthetic draft",
                 "inputSchema": {"type": "object", "properties": {}}}]

    def call_tool(self, principal, name, arguments):
        self.calls.append((principal, name, arguments))
        if name == "known_error":
            raise m.ConnectorError(409, "Draft version changed")
        if name == "leaky_error":
            raise m.ConnectorError(403, "Bearer synthetic-connection-only is private")
        if name == "exception":
            raise RuntimeError("traceback must not expose synthetic-private-value")
        return {"draftId": "synthetic-draft", "state": "pending_human_review"}

    def read_resource(self, principal, uri):
        if uri != "offerpath://synthetic/draft":
            raise m.ConnectorError(404, "Resource not found")
        return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": principal}]}

    def handle_http(self, method, path, headers, body):
        self.ui_calls.append((method, path, headers.get("Cookie"), body))
        if path == "/review":
            return (200, "text/html; charset=utf-8", b"Synthetic review",
                    {"Set-Cookie": "fixture=local; HttpOnly; SameSite=Strict",
                     "Cache-Control": "public", "Access-Control-Allow-Origin": "*"})
        return None


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        # Port reservation precedes handler construction so the Host guard sees
        # the actual ephemeral port, with no hard-coded or externally bound port.
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
        self.origin = "http://127.0.0.1:%d" % self.server.server_port
        self.server.RequestHandlerClass = m.make_handler(self.service, self.origin)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method="POST", path="/mcp", payload=None, headers=None, raw=None):
        values = {"Content-Type": "application/json",
                  "Accept": "application/json, text/event-stream",
                  "Authorization": "Bearer synthetic-connection-only"}
        values.update(headers or {})
        if payload is not None:
            raw = json.dumps(payload).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request(method, path, body=raw, headers=values)
            response = connection.getresponse()
            status, result_headers, data = response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()
        return status, result_headers, data

    def rpc(self, method, params=None, request_id=1, **kwargs):
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        status, headers, data = self.request(payload=message, **kwargs)
        return status, headers, json.loads(data)

    def test_initialize_negotiates_all_official_supported_versions(self):
        for version in m.SUPPORTED_VERSIONS:
            status, headers, data = self.rpc("initialize", {
                "protocolVersion": version, "capabilities": {},
                "clientInfo": {"name": "synthetic", "version": "1"}})
            self.assertEqual(status, 200)
            self.assertEqual(data["result"]["protocolVersion"], version)
            self.assertIn("tools", data["result"]["capabilities"])
            self.assertNotIn("Mcp-Session-Id", headers)

    def test_unknown_initial_version_negotiates_current(self):
        _, _, data = self.rpc("initialize", {"protocolVersion": "1900-01-01",
                                                "capabilities": {}, "clientInfo": {}})
        self.assertEqual(data["result"]["protocolVersion"], m.CURRENT_VERSION)

    def test_initialize_requires_fields(self):
        _, _, data = self.rpc("initialize", {"protocolVersion": "2025-11-25"})
        self.assertEqual(data["error"]["code"], -32602)

    def test_initialized_notification_is_empty_accepted(self):
        status, _, body = self.request(payload={"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual((status, body), (202, b""))

    def test_ping_and_tool_discovery(self):
        _, _, data = self.rpc("ping")
        self.assertEqual(data["result"], {})
        _, _, data = self.rpc("tools/list")
        self.assertEqual(data["result"]["tools"][0]["name"], "save_draft")

    def test_tool_call_includes_structured_and_text_results(self):
        status, _, data = self.rpc("tools/call", {"name": "save_draft", "arguments": {"job": "synthetic"}})
        result = data["result"]
        self.assertEqual(status, 200)
        self.assertFalse(result["isError"])
        self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])
        self.assertEqual(self.service.calls, [("synthetic-user", "save_draft", {"job": "synthetic"})])

    def test_old_version_has_text_result_without_new_structured_field(self):
        _, _, data = self.rpc("tools/call", {"name": "save_draft"},
                              headers={"MCP-Protocol-Version": "2025-03-26"})
        self.assertNotIn("structuredContent", data["result"])

    def test_tool_failures_are_results_not_tracebacks(self):
        for name, expected in (("known_error", "Draft version changed"),
                               ("exception", "Unable to complete this request")):
            status, _, data = self.rpc("tools/call", {"name": name})
            self.assertEqual(status, 200)
            self.assertTrue(data["result"]["isError"])
            self.assertEqual(data["result"]["content"][0]["text"], expected)
            self.assertNotIn("synthetic-private-value", json.dumps(data))
        _, _, data = self.rpc("tools/call", {"name": "leaky_error"})
        self.assertNotIn("synthetic-connection-only", json.dumps(data))

    def test_optional_resource_read(self):
        _, _, data = self.rpc("resources/read", {"uri": "offerpath://synthetic/draft"})
        self.assertEqual(data["result"]["contents"][0]["text"], "synthetic-user")
        _, _, data = self.rpc("resources/read", {"uri": "offerpath://missing"})
        self.assertEqual(data["error"]["code"], -32002)

    def test_unknown_method_and_invalid_tool_params(self):
        for method, params, code in (("unknown", {}, -32601),
                                      ("tools/call", {"name": "save_draft", "arguments": []}, -32602),
                                      ("resources/read", {}, -32602)):
            _, _, data = self.rpc(method, params)
            self.assertEqual(data["error"]["code"], code)
        self.assertFalse(self.service.calls)

    def test_parse_error_and_invalid_request(self):
        for raw, code in ((b"{", -32700), (b"[]", -32600),
                          (b'{"jsonrpc":"2.0","id":true,"method":"ping"}', -32600),
                          (b'{"jsonrpc":"2.0","id":1,"method":"ping","params":[]}', -32602),
                          (b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}', -32700),
                          (b'{"jsonrpc":"2.0","id":NaN,"method":"ping"}', -32700)):
            status, _, body = self.request(raw=raw)
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(body)["error"]["code"], code)

    def test_missing_wrong_or_duplicate_auth_never_calls_service(self):
        for auth in ("", "Basic fixture", "Bearer wrong", "Bearer two tokens"):
            status, headers, _ = self.request(payload={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                               headers={"Authorization": auth})
            self.assertEqual(status, 401)
            self.assertEqual(headers["WWW-Authenticate"], "Bearer")
        self.assertFalse(self.service.calls)

    def test_cross_origin_and_wrong_host_rejected_before_tools(self):
        for headers in ({"Origin": "https://evil.test"}, {"Origin": "null"},
                        {"Host": "evil.test:%d" % self.server.server_port},
                        {"Host": "127.0.0.1:1"},
                        {"Origin": self.origin + "/"},
                        {"Origin": "http://localhost:%d" % self.server.server_port}):
            status, _, _ = self.request(payload={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                        headers=headers)
            self.assertEqual(status, 403)
        self.assertFalse(self.service.calls)

    def test_same_origin_and_native_client_are_accepted(self):
        status, _, _ = self.rpc("ping", headers={"Origin": self.origin})
        self.assertEqual(status, 200)
        status, _, _ = self.rpc("ping")
        self.assertEqual(status, 200)

    def test_content_type_version_and_body_size(self):
        status, _, _ = self.rpc("ping", headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        status, _, _ = self.rpc("ping", headers={"MCP-Protocol-Version": "2099-01-01"})
        self.assertEqual(status, 400)
        status, _, _ = self.request(raw=b"", headers={"Content-Length": str(m.MAX_BODY_BYTES + 1)})
        self.assertEqual(status, 413)

    def test_no_sse_and_stateless_delete(self):
        status, headers, _ = self.request("GET")
        self.assertEqual(status, 405)
        self.assertEqual(headers["Allow"], "POST, DELETE")
        status, _, body = self.request("DELETE")
        self.assertEqual((status, body), (204, b""))
        status, _, _ = self.request("DELETE", headers={"Authorization": ""})
        self.assertEqual(status, 401)

    def test_ui_delegation_requires_origin_on_posts_and_retains_cookie(self):
        status, headers, body = self.request("GET", "/review", headers={"Cookie": "browser=synthetic"})
        self.assertEqual((status, body), (200, b"Synthetic review"))
        self.assertEqual(self.service.ui_calls[-1][2], "browser=synthetic")
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        status, _, _ = self.request("POST", "/review", raw=b"{}")
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/review", raw=b"{}", headers={"Origin": self.origin})
        self.assertEqual(status, 200)
        self.assertEqual(self.service.ui_calls[-1][3], b"{}")

    def test_security_headers_on_success_and_failure_no_unsafe_cors(self):
        for method, path in (("GET", "/review"), ("GET", "/missing"),
                             ("GET", "/mcp"), ("PUT", "/mcp")):
            _, headers, _ = self.request(method, path)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
            self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_no_request_content_logging(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            self.rpc("tools/call", {"name": "exception", "arguments": {"private": "fixture"}})
            self.request("GET", "/private-fixture-path")
        self.assertEqual(output.getvalue(), "")


class ConfigurationTests(unittest.TestCase):
    def test_public_or_credentialed_base_url_is_not_supported(self):
        for url in ("https://example.test", "http://0.0.0.0:4318", "http://127.0.0.1:0",
                    "http://user:pass@127.0.0.1:4318", "http://127.0.0.1:4318/path"):
            with self.assertRaises(ValueError):
                m.make_handler(FakeService(), url)


if __name__ == "__main__":
    unittest.main()
