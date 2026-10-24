"""Synthetic HTTP fixtures for the scoped adapter; no real OfferPath requests."""

import contextlib
import importlib.util
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "qwen_remote", Path(__file__).parents[1] / "scripts/qwen_remote.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.server.requests.append((self.command, self.path, dict(self.headers), b""))
        if self.server.mode == "redirect":
            self.send_response(302)
            self.send_header("Location", self.server.redirect)
            self.end_headers()
            return
        if self.server.mode == "error":
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"PRIVATE UPSTREAM TOKEN synthetic-only-token")
            return
        if self.server.mode == "oversize_header":
            self.send_response(200)
            self.send_header("Content-Length", str(m.MAX_RECORD_BYTES + 1))
            self.end_headers()
            return
        if self.path.endswith("/resume"):
            data = self.server.pdf
        else:
            data = self.server.rows_raw
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        if self.server.mode != "no_length":
            self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_PUT(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.requests.append((self.command, self.path, dict(self.headers), body))
        if self.path.endswith("/resume"):
            self.server.pdf = body
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")


class RemoteTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        self.server.mode = "ok"
        self.server.requests = []
        self.server.pdf = b"%PDF-1.4 synthetic fixture, not a real application"
        self.server.rows_raw = json.dumps([{"id": "synthetic_1", "company": "Example Co",
                                            "role": "Engineer", "resume_version": 0}]).encode()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = "http://127.0.0.1:%d" % self.server.server_port
        self.api = m.RemoteOfferPath(self.origin, "synthetic-only-token", allow_http=True)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_rows_read_and_record_write_contract(self):
        self.assertFalse(self.api.synthetic)
        self.assertEqual(self.api.base, self.origin)
        self.assertEqual(self.api.rows()[0]["id"], "synthetic_1")
        body = b'{"id":"synthetic_1","company":"Example Co","role":"Engineer"}'
        self.assertEqual(self.api.request("/api/applications/synthetic_1", "PUT", body,
                                         {"content-type": "application/json"}), b"{}")
        self.assertEqual(self.server.requests[-1][0:2], ("PUT", "/api/applications/synthetic_1"))
        self.assertEqual(self.server.requests[-1][3], body)

    def test_pdf_upload_preserves_encoded_filename_and_version(self):
        pdf = b"%PDF-1.4 synthetic tailored bytes"
        path = "/api/applications/synthetic_1/resume"
        self.api.request(path, "PUT", pdf, {"content-type": "application/pdf",
                         "x-resume-name": "%E5%90%88%E6%88%90.pdf", "if-match": "0"})
        headers = {name.lower(): value for name, value in self.server.requests[-1][2].items()}
        self.assertEqual(headers["x-resume-name"], "%E5%90%88%E6%88%90.pdf")
        self.assertEqual(headers["if-match"], "0")
        self.assertEqual(self.api.request(path), pdf)

    def test_client_headers_cannot_replace_authorization_host_or_accept(self):
        self.api.request("/api/applications", headers={"authorization": "Bearer attacker",
                         "HOST": "evil.test", "Accept": "text/html"})
        headers = {name.lower(): value for name, value in self.server.requests[-1][2].items()}
        self.assertEqual(headers["authorization"], "Bearer synthetic-only-token")
        self.assertEqual(headers["host"], self.origin[7:])
        self.assertEqual(headers["accept"], "application/json")

    def test_scope_and_method_validation_prevents_requests(self):
        for path in ("https://evil.test/api/applications", "//evil.test/api/applications",
                     "/api/applications/../secret", "/api/applications/x?token=y",
                     "/api/applications/x#fragment", "/api/applications/x/resume/extra",
                     "/api/applications/x%2fresume", "/api/applications/x/", "/api/settings"):
            with self.assertRaises(m.RemoteError):
                self.api.request(path)
        for method in ("POST", "DELETE", "PATCH", "get"):
            with self.assertRaises(m.RemoteError):
                self.api.request("/api/applications", method)
        self.assertEqual(self.server.requests, [])

    def test_redirect_is_refused_without_following_same_or_other_origin(self):
        self.server.mode = "redirect"
        for target in (self.origin + "/api/applications/synthetic_1", "https://evil.test/steal"):
            self.server.redirect = target
            before = len(self.server.requests)
            with self.assertRaisesRegex(m.RemoteError, "重定向"):
                self.api.rows()
            self.assertEqual(len(self.server.requests), before + 1)

    def test_upstream_errors_never_return_private_body_or_token(self):
        self.server.mode = "error"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(m.RemoteError) as caught:
                self.api.rows()
        message = str(caught.exception)
        self.assertEqual(caught.exception.status, 401)
        self.assertNotIn("PRIVATE", message)
        self.assertNotIn("synthetic-only-token", message)
        self.assertEqual(stderr.getvalue(), "")

    def test_declared_and_undeclared_oversize_records_rejected(self):
        self.server.mode = "oversize_header"
        with self.assertRaisesRegex(m.RemoteError, "大小限制"):
            self.api.rows()
        self.server.mode = "no_length"
        self.server.rows_raw = b" " * (m.MAX_RECORD_BYTES + 1)
        with self.assertRaisesRegex(m.RemoteError, "大小限制"):
            self.api.rows()

    def test_oversize_pdf_and_outbound_payloads_rejected(self):
        self.server.pdf = b"x" * (m.MAX_PDF_BYTES + 1)
        with self.assertRaisesRegex(m.RemoteError, "大小限制"):
            self.api.request("/api/applications/synthetic_1/resume")
        before = len(self.server.requests)
        with self.assertRaisesRegex(m.RemoteError, "大小限制"):
            self.api.request("/api/applications/synthetic_1/resume", "PUT", self.server.pdf)
        self.assertEqual(len(self.server.requests), before)

    def test_rows_reject_bad_schema_duplicates_and_nonfinite_json(self):
        fixtures = [b"{}", b"[1]", b"[{\"id\":\"bad/id\",\"company\":\"C\",\"role\":\"R\"}]",
                    b"[{\"id\":\"x\",\"company\":\"\",\"role\":\"R\"}]",
                    b"[{\"id\":\"x\",\"company\":\"C\",\"role\":\"R\",\"resume_version\":true}]",
                    b"[{\"id\":\"x\",\"company\":\"C\",\"role\":\"R\",\"location\":1}]",
                    b"NaN", b"not json", b"\xff"]
        one = {"id": "x", "company": "C", "role": "R"}
        fixtures.append(json.dumps([one, one]).encode())
        for fixture in fixtures:
            self.server.rows_raw = fixture
            with self.assertRaises(m.RemoteError):
                self.api.rows()

    def test_request_body_and_header_controls_are_rejected(self):
        for data, method in (({}, "PUT"), (None, "PUT"), (b"body", "GET")):
            with self.assertRaises(m.RemoteError):
                self.api.request("/api/applications/x", method, data)
        for headers in ({"x-resume-name": "name\r\nAuthorization: leaked"}, {"bad\nname": "x"},
                        {"if-match": 1}, {"Authorization": "bad\nvalue"}):
            with self.assertRaises(m.RemoteError):
                self.api.request("/api/applications/x", headers=headers)
        self.assertEqual(self.server.requests, [])


class ConfigurationTests(unittest.TestCase):
    def test_https_origin_required_and_test_http_only_loopback(self):
        for origin in ("http://example.test", "https://user:pass@example.test", "https://example.test/",
                       "https://example.test/path", "https://example.test?token=private",
                       "https://example.test#private", "https://example.test:0",
                       "https://example.test?", "https://example.test#", "https://example.test:",
                       " https://example.test", "https://exam\nple.test", "https://example.test\\evil"):
            with self.assertRaises(m.RemoteError):
                m.RemoteOfferPath(origin, "fixture")
        with self.assertRaises(m.RemoteError):
            m.RemoteOfferPath("http://example.test", "fixture", allow_http=True)
        m.RemoteOfferPath("https://example.test", "fixture")
        m.RemoteOfferPath("http://localhost:1234", "fixture", allow_http=True)

    def test_tokens_reject_empty_controls_whitespace_and_nonascii_without_exposure(self):
        for token in ("", "fixture\r\nleak", "fixture\x00", "fixture\x7f", "fixture space", "非ASCII", None):
            with self.assertRaises(m.RemoteError) as caught:
                m.RemoteOfferPath("https://example.test", token)
            self.assertNotIn("fixture", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
