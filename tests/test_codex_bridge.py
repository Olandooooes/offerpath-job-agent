"""Actual child-process MCP checks with synthetic data and no model account."""

import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import select
import signal
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from http.cookies import SimpleCookie
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/codex_bridge.py'
sys.path.insert(0, str(ROOT / 'scripts'))
import codex_bridge as m


class MetaParser(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.csrf = None
        self.feed(page)

    def handle_starttag(self, tag, values):
        attrs = dict(values)
        if tag == 'meta' and attrs.get('name') == 'csrf':
            self.csrf = attrs.get('content')


class Client:
    def __init__(self, workspace):
        self.process = subprocess.Popen([sys.executable, str(SCRIPT), 'stdio', '--workspace', str(workspace)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        bufsize=0)
        self.counter = 0
        self.buffer = b''

    def send(self, value):
        self.process.stdin.write(json.dumps(value, ensure_ascii=False).encode() + b'\n')
        self.process.stdin.flush()

    def read(self, timeout=10):
        while b'\n' not in self.buffer:
            ready = select.select([self.process.stdout], [], [], timeout)[0]
            if not ready:
                raise AssertionError('MCP child did not respond within its bound')
            part = os.read(self.process.stdout.fileno(), 65536)
            if not part:
                raise AssertionError('MCP child closed stdout unexpectedly')
            self.buffer += part
        line, self.buffer = self.buffer.split(b'\n', 1)
        return json.loads(line)

    def rpc(self, method, params=None):
        self.counter += 1
        message = dict(jsonrpc='2.0', id=self.counter, method=method)
        if params is not None:
            message['params'] = params
        self.send(message)
        result = self.read()
        if result.get('id') != self.counter:
            raise AssertionError('Unexpected protocol reply')
        return result

    def tool(self, name, args=None):
        result = self.rpc('tools/call', dict(name=name, arguments=args or {}))['result']
        return result, result.get('structuredContent')

    def initialize(self, version='2025-11-25'):
        return self.rpc('initialize', dict(protocolVersion=version, capabilities={},
                                           clientInfo=dict(name='synthetic-codex-host', version='test')))

    def close(self, terminate=False):
        if self.process.stderr.closed:
            return b'', b''
        if self.process.poll() is None:
            if terminate:
                self.process.send_signal(signal.SIGTERM)
            else:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
                raise AssertionError('MCP child did not close its resources')
        stderr = self.process.stderr.read()
        remaining = self.buffer + (b'' if self.process.stdout.closed else self.process.stdout.read())
        if not self.process.stdout.closed:
            self.process.stdout.close()
        self.process.stderr.close()
        if not self.process.stdin.closed:
            self.process.stdin.close()
        self.buffer = b''
        return stderr, remaining


class CodexBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.private = Path(self.temp.name) / 'synthetic-private'
        m.init_workspace(self.private)
        self.clients = []
        self.cookies = {}

    def tearDown(self):
        for client in self.clients:
            client.close()
        self.temp.cleanup()

    def client(self):
        client = Client(self.private)
        self.clients.append(client)
        client.initialize()
        return client

    def cli(self, *arguments):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, arguments)],
                              capture_output=True, timeout=10)

    def draft(self, client):
        result, context = client.tool('get_context', {'job_id': 'demo-integration'})
        self.assertFalse(result['isError'])
        facts = [f for f in context['facts'] if f['id'] in ('fact-1', 'fact-3')]
        arguments = dict(context_id=context['context_id'],
                         summary=dict(text=facts[0]['details'], fact_ids=['fact-1']),
                         items=[dict(fact_id=f['id'], title=f['title'], text=f['details']) for f in facts],
                         mapping=[dict(requirement_index=i, fact_id=value)
                                  for i, value in enumerate(['fact-1', 'fact-1', 'fact-3', None])],
                         changes=['合成测试：按接口与数据质量岗位调整经历顺序'])
        result, package = client.tool('save_draft', arguments)
        self.assertFalse(result['isError'], result)
        return package

    def request(self, origin, method, path, payload=None, headers=None):
        parsed = urlsplit(origin)
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
        values = {'Origin': origin}
        values.update(headers or {})
        if self.cookies:
            values['Cookie'] = '; '.join(key + '=' + value for key, value in self.cookies.items())
        body = None
        if payload is not None:
            values['Content-Type'] = 'application/json'
            body = json.dumps(payload).encode()
        try:
            connection.request(method, path, body=body, headers=values)
            response = connection.getresponse()
            data = response.read()
            for key, value in response.getheaders():
                if key.lower() == 'set-cookie':
                    cookie = SimpleCookie()
                    cookie.load(value)
                    self.cookies.update({name: morsel.value for name, morsel in cookie.items()})
            return response.status, data
        finally:
            connection.close()

    def login(self, origin):
        status, page = self.request(origin, 'GET', '/')
        self.assertEqual(status, 200)
        csrf = MetaParser(page.decode()).csrf
        secret = json.loads((self.private / 'secrets.json').read_text())
        status, response = self.request(origin, 'POST', '/session',
                                        dict(csrf=csrf, code=secret['review_code']))
        self.assertEqual(status, 200, response)
        status, response = self.request(origin, 'GET', '/state')
        self.assertEqual(status, 200)
        return json.loads(response)['csrf']

    def test_stdio_initialize_notifications_tools_and_no_stdout_logging(self):
        client = self.client()
        client.send(dict(jsonrpc='2.0', method='notifications/initialized'))
        client.send(dict(jsonrpc='2.0', method='notifications/synthetic-unknown'))
        result = client.rpc('tools/list')
        names = [tool['name'] for tool in result['result']['tools']]
        self.assertIn('get_context', names)
        self.assertIn('sync_records', names)
        self.assertNotIn('approve', names)
        self.assertNotIn('apply', names)
        self.assertEqual(client.rpc('ping')['result'], {})
        self.assertEqual(client.close(), (b'', b''))
        self.assertEqual(client.process.returncode, 0)

    def test_actual_pdf_resources_approval_and_record_persistence_after_restart(self):
        client = self.client()
        package = self.draft(client)
        identity = package['package_id']
        old_origin = package['review_url'].split('/review?', 1)[0]
        self.assertNotEqual(urlsplit(old_origin).port, 4327)
        resource = client.rpc('resources/read', {'uri': package['resource_uri']})['result']
        pdf = base64.b64decode(resource['contents'][0]['blob'])
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertEqual(hashlib.sha256(pdf).hexdigest(), package['sha256'])
        result, _ = client.tool('report_application', dict(package_id=identity, outcome='user_reported',
                                                         same_attachment=True, receipt='SYNTHETIC only'))
        self.assertTrue(result['isError'])
        result, _ = client.tool('approve', {'package_id': identity})
        self.assertTrue(result['isError'])
        # Model bearer access and resources/read cannot turn into human consent.
        secret = json.loads((self.private / 'secrets.json').read_text())
        status, _ = self.request(old_origin, 'POST', '/approve', dict(package_id=identity),
                                  {'Authorization': 'Bearer ' + secret['bridge_token']})
        self.assertIn(status, (401, 403))
        csrf = self.login(old_origin)
        approval = dict(package_id=identity, version=package['version'], sha256=package['sha256'], csrf=csrf)
        status, _ = self.request(old_origin, 'POST', '/approve', approval)
        self.assertEqual(status, 409)
        status, browser_pdf = self.request(old_origin, 'GET', '/pdf/' + identity)
        self.assertEqual((status, browser_pdf), (200, pdf))
        self.assertEqual(self.request(old_origin, 'POST', '/approve', approval)[0], 200)
        result, _ = client.tool('report_application', dict(package_id=identity, outcome='user_reported',
                                                         same_attachment=True, receipt='SYNTHETIC; no real submission'))
        self.assertFalse(result['isError'])
        result, record = client.tool('sync_records', {'package_id': identity})
        self.assertFalse(result['isError'])
        self.assertEqual(record['state'], 'bytes_verified')
        self.assertEqual(client.close(), (b'', b''))
        self.assert_port_closed(old_origin)
        # Occupy the old port so the new process cannot accidentally pick it.
        from http.server import BaseHTTPRequestHandler, HTTPServer
        reservation = HTTPServer(('127.0.0.1', urlsplit(old_origin).port), BaseHTTPRequestHandler)
        try:
            second = self.client()
            result, restored = second.tool('get_pdf', {'package_id': identity})
            self.assertFalse(result['isError'])
            self.assertTrue(restored['approved'])
            self.assertEqual(restored['sha256'], package['sha256'])
            self.assertEqual(restored['version'], package['version'])
            self.assertEqual(restored['approval']['sha256'], package['sha256'])
            new_origin = restored['review_url'].split('/review?', 1)[0]
            self.assertNotEqual(new_origin, old_origin)
            self.assertTrue(restored['pdf_url'].startswith(new_origin))
            result, rows = second.tool('list_records')
            self.assertFalse(result['isError'])
            self.assertEqual(len(rows['records']), 1)
            self.assertTrue(rows['records'][0]['archive_url'].startswith(new_origin))
            self.assertEqual(rows['records'][0]['sha256'], package['sha256'])
            result = second.rpc('resources/read', {'uri': package['resource_uri']})['result']
            self.assertEqual(base64.b64decode(result['contents'][0]['blob']), pdf)
            self.assertEqual(second.close(), (b'', b''))
            self.assert_port_closed(new_origin)
        finally:
            reservation.server_close()

    def assert_port_closed(self, origin):
        parsed = urlsplit(origin)
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=1)
        try:
            with self.assertRaises(OSError):
                connection.request('GET', '/')
        finally:
            connection.close()

    def test_sigterm_closes_loopback_and_sqlite(self):
        client = self.client()
        package = self.draft(client)
        origin = package['review_url'].split('/review?', 1)[0]
        self.assertEqual(client.close(terminate=True), (b'', b''))
        self.assertEqual(client.process.returncode, 0)
        self.assert_port_closed(origin)
        with sqlite3.connect(self.private / 'db.sqlite3', timeout=1) as db:
            db.execute('BEGIN EXCLUSIVE')
            db.rollback()

    def test_broken_stdout_pipe_also_closes_review_service(self):
        client = self.client()
        package = self.draft(client)
        origin = package['review_url'].split('/review?', 1)[0]
        client.process.stdout.close()
        client.send(dict(jsonrpc='2.0', id=999, method='ping'))
        client.process.wait(timeout=10)
        self.assert_port_closed(origin)
        self.assertEqual(client.close(), (b'', b''))
        self.assertEqual(client.process.returncode, 0)

    def test_malformed_json_invalid_ids_duplicates_and_errors_are_sanitized(self):
        client = self.client()
        for raw, code in ((b'{\n', -32700), (b'[]\n', -32600),
                          (b'{"jsonrpc":"2.0","id":true,"method":"ping"}\n', -32600),
                          (b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}\n', -32700),
                          (b'{"jsonrpc":"2.0","id":NaN,"method":"ping"}\n', -32700)):
            client.process.stdin.write(raw)
            client.process.stdin.flush()
            self.assertEqual(client.read()['error']['code'], code)
        result = client.rpc('resources/read', {'uri': 'offerpath://pdf/not-a-real-private-pdf'})
        self.assertEqual(result['error']['code'], -32002)
        serialized = json.dumps(result)
        self.assertNotIn(str(self.private), serialized)
        self.assertNotIn('Traceback', serialized)
        self.assertEqual(client.close(), (b'', b''))

    def test_oversized_message_terminates_bounded_transport(self):
        client = self.client()
        # A single malicious line is bounded and closes the server, without
        # waiting for the attacker to finish the rest of its payload.
        client.process.stdin.write(b' ' * (m.MAX_BODY_BYTES + 1))
        client.process.stdin.flush()
        self.assertEqual(client.read()['error']['code'], -32600)
        client.process.wait(timeout=10)
        self.assertEqual(client.close(), (b'', b''))

    def test_old_mcp_version_retains_legacy_result_format(self):
        client = Client(self.private)
        self.clients.append(client)
        self.assertEqual(client.initialize('2025-03-26')['result']['protocolVersion'], '2025-03-26')
        result, _ = client.tool('list_jobs')
        self.assertNotIn('structuredContent', result)
        self.assertFalse(result['isError'])

    def test_cli_config_is_private_path_only_and_never_overwrites(self):
        output = Path(self.temp.name) / 'codex connector.toml'
        result = self.cli('config', '--workspace', self.private, '--output', output)
        self.assertEqual(result.returncode, 0, result.stderr)
        content = output.read_text()
        self.assertIn('[mcp_servers.offerpath]', content)
        command = json.loads(content.split('command = ', 1)[1].splitlines()[0])
        args = json.loads(content.split('args = ', 1)[1].splitlines()[0])
        self.assertEqual(command, str(Path(sys.executable).absolute()))
        self.assertEqual(args, [str(SCRIPT.resolve()), 'stdio', '--workspace', str(self.private.resolve())])
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        secret = json.loads((self.private / 'secrets.json').read_text())
        for value in (secret['bridge_token'], secret['review_code']):
            self.assertNotIn(value, content + result.stdout.decode() + result.stderr.decode())
        result = self.cli('config', '--workspace', self.private, '--output', output)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_text(), content)
        self.assertNotIn(str(output), result.stderr.decode())

    def test_cli_config_rejects_git_output_and_status_has_no_credentials(self):
        fake_repo = Path(self.temp.name) / 'fake-repo'
        (fake_repo / '.git').mkdir(parents=True)
        output = fake_repo / 'private-config.toml'
        result = self.cli('config', '--workspace', self.private, '--output', output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        result = self.cli('status', '--workspace', self.private)
        self.assertEqual(result.returncode, 0)
        status = json.loads(result.stdout)
        self.assertEqual(status['model_api_calls'], 0)
        self.assertEqual(status['transport'], 'stdio')
        self.assertNotIn('token', result.stdout.decode())
        self.assertNotIn(str(self.private), result.stdout.decode())

    @unittest.skipIf(os.name == 'nt', 'Symlink creation on Windows requires OS privileges')
    def test_generated_config_preserves_virtualenv_interpreter_symlink(self):
        executable = Path(self.temp.name) / 'example-venv' / 'bin' / 'python'
        executable.parent.mkdir(parents=True)
        executable.symlink_to(sys.executable)
        output = Path(self.temp.name) / 'venv-connector.toml'
        result = subprocess.run([str(executable), str(SCRIPT), 'config', '--workspace',
                                 str(self.private), '--output', str(output)],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        command = json.loads(output.read_text().split('command = ', 1)[1].splitlines()[0])
        self.assertEqual(command, str(executable.absolute()))
        self.assertNotEqual(command, str(executable.resolve()))

    def test_cli_init_failure_and_missing_workspace_do_not_echo_arguments(self):
        result = self.cli('init', '--workspace', self.private)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(str(self.private), result.stderr.decode())
        result = self.cli('stdio', '--workspace', Path(self.temp.name) / 'missing')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'')
        self.assertNotIn('Traceback', result.stderr.decode())
        result = self.cli('config', '--workspace', self.private, '--accidental-secret', 'synthetic-private-value')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('synthetic-private-value', result.stderr.decode())

    def test_second_process_same_workspace_cannot_move_first_process_routes(self):
        first = self.client()
        package = self.draft(first)
        second = Client(self.private)
        self.clients.append(second)
        second.process.stdin.close()
        second.process.wait(timeout=10)
        stderr, stdout = second.close()
        self.assertNotEqual(second.process.returncode, 0)
        self.assertEqual(stdout, b'')
        self.assertIn('已被另一个Codex连接器使用', stderr.decode())
        self.assertNotIn(str(self.private), stderr.decode())
        result, restored = first.tool('get_pdf', {'package_id': package['package_id']})
        self.assertFalse(result['isError'])
        self.assertEqual(restored['review_url'], package['review_url'])
        self.assertEqual(restored['sha256'], package['sha256'])
        self.assertEqual(first.close(), (b'', b''))
        restarted = self.client()
        result, restored = restarted.tool('get_pdf', {'package_id': package['package_id']})
        self.assertFalse(result['isError'])
        self.assertEqual(restored['sha256'], package['sha256'])


if __name__ == '__main__':
    unittest.main()
