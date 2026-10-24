"""Narrow HTTPS client for the existing OfferPath records/attachments API.

Credentials belong to the user's private connector workspace, never to a skill
prompt or MCP result. This client does not load credentials, follow redirects,
call a model, submit a job application, or log requests/responses.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request


MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_PDF_BYTES = 1024 * 1024
MAX_RECORDS = 5000
REQUEST_TIMEOUT = 30
PATH = re.compile(r"/api/applications(?:/[A-Za-z0-9_-]+(?:/resume)?)?\Z")
IDENTITY = re.compile(r"[A-Za-z0-9_-]{1,256}\Z")


class RemoteError(RuntimeError):
    """Public error without upstream payloads or credentials."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.message = message
        self.status = status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


def _fail(message):
    raise RemoteError(message)


def _has_control(value):
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _reject_constant(value):
    raise ValueError("Invalid JSON number")


class RemoteOfferPath:
    synthetic = False

    def __init__(self, base_url, token, allow_http=False):
        if (not isinstance(base_url, str) or not base_url or len(base_url) > 400
                or base_url != base_url.strip() or _has_control(base_url)
                or any(char in base_url for char in ("\\", "?", "#"))):
            _fail("OfferPath 地址必须是无路径的 HTTPS 源站")
        try:
            parsed = urllib.parse.urlsplit(base_url)
            port = parsed.port
            permitted = parsed.scheme == "https" or (
                allow_http is True and parsed.scheme == "http"
                and parsed.hostname in ("127.0.0.1", "localhost"))
            valid = (permitted and parsed.hostname and not parsed.username
                     and not parsed.password and not parsed.path and not parsed.query
                     and not parsed.fragment and (port is None or 1 <= port <= 65535)
                     and not any(char.isspace() for char in parsed.netloc)
                     and "@" not in parsed.netloc and not parsed.netloc.endswith(":"))
        except (ValueError, TypeError):
            valid = False
        if not valid:
            _fail("OfferPath 地址必须是无路径的 HTTPS 源站")
        if (not isinstance(token, str) or not 1 <= len(token) <= 4096
                or _has_control(token) or any(char.isspace() for char in token)):
            _fail("OfferPath 连接令牌格式不合格")
        # urllib requires HTTP header values to be Latin-1. Real bearer tokens
        # are ASCII; reject unsupported values here without printing the token.
        try:
            token.encode("ascii")
        except UnicodeEncodeError:
            _fail("OfferPath 连接令牌格式不合格")
        self.base = base_url
        self._token = token
        # Do not inherit a machine's proxy configuration: this scoped credential
        # must be sent only to the origin explicitly selected by its owner.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def request(self, path, method="GET", data=None, headers=None):
        if not isinstance(path, str) or len(path) > 1000 or not PATH.fullmatch(path):
            _fail("仅允许 OfferPath 投递记录与简历附件接口")
        if method not in ("GET", "PUT"):
            _fail("仅允许读取或同步 OfferPath 记录与附件")
        if data is not None and not isinstance(data, bytes):
            _fail("同步内容必须是已核验的文件字节")
        if method == "GET" and data is not None:
            _fail("读取请求不得携带同步内容")
        if method == "PUT" and data is None:
            _fail("同步请求缺少内容")
        limit = MAX_PDF_BYTES if path.endswith("/resume") else MAX_RECORD_BYTES
        if data is not None and len(data) > limit:
            _fail("OfferPath 同步内容超过大小限制")
        outgoing = {}
        if headers is not None:
            if not isinstance(headers, dict):
                _fail("同步请求头格式不合格")
            for name, value in headers.items():
                if (not isinstance(name, str) or not isinstance(value, str)
                        or not re.fullmatch(r"[A-Za-z0-9!#$%&'*+.^_`|~-]+", name)
                        or _has_control(value)):
                    _fail("同步请求头格式不合格")
                if name.lower() in ("content-type", "x-resume-name", "if-match"):
                    outgoing[name.lower()] = value
        outgoing.update({
            "Authorization": "Bearer " + self._token,
            "Accept": "application/pdf" if path.endswith("/resume") else "application/json",
            "User-Agent": "OfferPath-Job-Agent/QwenWork-0.1",
        })
        try:
            request = urllib.request.Request(self.base + path, data=data, method=method,
                                             headers=outgoing)
            with self._opener.open(request, timeout=REQUEST_TIMEOUT) as response:
                # A custom opener cannot silently transform an origin redirect.
                if response.geturl() != self.base + path or not 200 <= response.status <= 299:
                    _fail("OfferPath 返回了不允许的响应；仅补同步，不重新投递")
                lengths = response.headers.get_all("Content-Length", [])
                if lengths and (len(lengths) != 1 or not re.fullmatch(r"[0-9]+", lengths[0])
                                or len(lengths[0]) > 10 or int(lengths[0]) > limit):
                    _fail("OfferPath 返回内容超过大小限制")
                content = response.read(limit + 1)
                if len(content) > limit:
                    _fail("OfferPath 返回内容超过大小限制")
                return content
        except RemoteError:
            raise
        except urllib.error.HTTPError as error:
            # Never read or expose an upstream error body, URL, headers or token.
            error.close()
            if error.code in (301, 302, 303, 307, 308):
                _fail("OfferPath 重定向已拒绝；请核对源站地址")
            if error.code in (401, 403):
                raise RemoteError("OfferPath 授权不可用，请本人检查连接", 401) from None
            if error.code in (409, 412):
                raise RemoteError("OfferPath 记录或附件已变化；请核对后仅补同步", 409) from None
            _fail("OfferPath 请求失败；保留材料，仅补同步，不重新投递")
        except Exception:
            raise RemoteError("OfferPath 连接失败；保留材料，仅补同步，不重新投递") from None

    def rows(self):
        try:
            rows = json.loads(self.request("/api/applications").decode("utf-8"),
                              parse_constant=_reject_constant)
        except RemoteError:
            raise
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise RemoteError("OfferPath 记录格式不合格") from None
        if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
            _fail("OfferPath 记录格式不合格")
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                _fail("OfferPath 记录格式不合格")
            identity = row.get("id")
            if (not isinstance(identity, str) or not IDENTITY.fullmatch(identity)
                    or identity in seen):
                _fail("OfferPath 记录身份不合格")
            seen.add(identity)
            for key in ("company", "role"):
                if not isinstance(row.get(key), str) or not row[key].strip() or len(row[key]) > 1000:
                    _fail("OfferPath 记录公司或岗位不合格")
            for key in ("location", "url", "notes", "stage", "resume_name", "applied_at"):
                if row.get(key) is not None and (not isinstance(row[key], str) or len(row[key]) > 100000):
                    _fail("OfferPath 记录字段格式不合格")
            if row.get("resume_version") is not None and (
                    type(row["resume_version"]) is not int or row["resume_version"] < 0):
                _fail("OfferPath 附件版本格式不合格")
        return rows
