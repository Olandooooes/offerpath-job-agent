"""Codex STDIO MCP entry point with a process-owned local PDF review card.

No model API is called. The shared connector owns facts, immutable PDFs, human
approval and record synchronization. This entry point only translates the MCP
transport and starts/stops the loopback review service with the client process.
"""

import argparse
import http.client
import json
import os
from pathlib import Path
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from qwen_transport import (CURRENT_VERSION, MAX_BODY_BYTES, ConnectorError,
                            _pairs, _reject_constant, make_handler)
from qwenwork import QwenService, init_workspace, outside


MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def rpc_error(identity, code, message):
    return dict(jsonrpc='2.0', id=identity, error=dict(code=code, message=message))


class WorkspaceBusy(Exception):
    pass


class WorkspaceLease:
    """A private OS advisory lock; process death also releases ownership."""

    def __init__(self, workspace):
        self.stream = None
        workspace = safe_path(workspace)
        if not workspace.is_dir():
            raise ConnectorError(400, 'Initialize the private workspace first')
        flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(str(workspace / '.codex-bridge.lock'), flags, 0o600)
        try:
            if hasattr(os, 'fchmod'):
                os.fchmod(descriptor, 0o600)
            self.stream = os.fdopen(descriptor, 'r+b', buffering=0)
            if os.name == 'nt':
                import msvcrt
                if self.stream.seek(0, 2) == 0:
                    self.stream.write(b'0')
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if self.stream is not None:
                self.stream.close()
                self.stream = None
            else:
                os.close(descriptor)
            raise WorkspaceBusy() from None

    def close(self):
        if self.stream is not None:
            self.stream.close()  # Closing the handle releases the OS lock.
            self.stream = None


class CodexService(QwenService):
    """Refresh process-local routes without changing facts, approvals or PDFs."""

    def __init__(self, workspace, base_url):
        super().__init__(workspace, base_url)
        # Dynamic ports must not leave stale links after a client restart. Only
        # these generated routes move; approval hashes, versions and outcomes do
        # not depend on the process-local origin and must remain unchanged.
        with self.lock:
            state = self.state()
            changed = False
            for identity, package in state['packages'].items():
                routes = dict(pdf_url=base_url + '/pdf/' + identity,
                              review_url=base_url + '/review?id=' + identity)
                if any(package.get(key) != value for key, value in routes.items()):
                    package.update(routes)
                    changed = True
            for collection in (state['records'].values(), state.get('history_records', [])):
                for record in collection:
                    route = base_url + '/archive/' + record['package_id']
                    if record.get('archive_url') != route:
                        record['archive_url'] = route
                        changed = True
            if changed:
                self.save(state)


class LocalBridge:
    """Own the listening socket, request workers and SQLite connection."""

    def __init__(self, workspace):
        self.server = self.service = self.thread = self.lease = None
        try:
            # Independent Codex tasks must not compete to update one SQLite
            # state or rewrite one another's process-local review URLs.
            self.lease = WorkspaceLease(workspace)
            self.server = ThreadingHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler)
            self.base_url = 'http://127.0.0.1:%d' % self.server.server_port
            self.service = CodexService(workspace, self.base_url)
            self.server.RequestHandlerClass = make_handler(self.service, self.base_url)
            # Join in-flight requests before closing SQLite. These threads are
            # bounded by the shared HTTP transport's socket timeout.
            self.server.daemon_threads = False
            self.thread = threading.Thread(target=self.server.serve_forever,
                                           kwargs={'poll_interval': 0.05}, daemon=True)
            self.thread.start()
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.thread is not None:
            self.server.shutdown()
            self.thread.join(timeout=2)
            self.thread = None
        if self.server is not None:
            self.server.server_close()
            self.server = None
        if self.service is not None:
            with self.service.lock:
                self.service.db.close()
            self.service = None
        if self.lease is not None:
            self.lease.close()
            self.lease = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def forward(self, raw, version):
        connection = http.client.HTTPConnection('127.0.0.1',
                                               int(self.base_url.rsplit(':', 1)[1]),
                                               timeout=30)
        try:
            connection.request('POST', '/mcp', body=raw, headers={
                'Content-Type': 'application/json', 'Accept': 'application/json',
                'MCP-Protocol-Version': version,
                'Authorization': 'Bearer ' + self.service.secret['bridge_token'],
            })
            response = connection.getresponse()
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if response.status == 202 and not body:
                return None
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError('Response exceeds transport bound')
            value = json.loads(body.decode('utf-8'), parse_constant=_reject_constant,
                               object_pairs_hook=_pairs)
            if not isinstance(value, dict) or value.get('jsonrpc') != '2.0':
                raise ValueError('Invalid local response')
            return value
        finally:
            connection.close()


def run_stdio(workspace, input_stream=None, output_stream=None):
    """Read newline-delimited JSON-RPC; stdout contains only JSON-RPC replies."""
    input_stream = input_stream if input_stream is not None else sys.stdin.buffer
    output_stream = output_stream if output_stream is not None else sys.stdout.buffer
    version = CURRENT_VERSION

    def send(value):
        output_stream.write(json_bytes(value) + b'\n')
        output_stream.flush()

    with LocalBridge(workspace) as bridge:
        while True:
            raw = input_stream.readline(MAX_BODY_BYTES + 1)
            if not raw:
                return
            # Refuse the connection rather than accumulating or draining an
            # unbounded line. MCP messages may not contain literal newlines.
            if len(raw) > MAX_BODY_BYTES:
                send(rpc_error(None, -32600, 'Message exceeds transport limit'))
                return
            try:
                message = json.loads(raw.decode('utf-8'), parse_constant=_reject_constant,
                                     object_pairs_hook=_pairs)
            except (UnicodeDecodeError, ValueError, RecursionError):
                send(rpc_error(None, -32700, 'Parse error'))
                continue
            notification = (isinstance(message, dict) and 'id' not in message
                            and message.get('jsonrpc') == '2.0'
                            and isinstance(message.get('method'), str)
                            and bool(message['method']))
            identity = message.get('id') if isinstance(message, dict) else None
            if not isinstance(identity, (str, int)) or isinstance(identity, bool):
                identity = None
            try:
                reply = bridge.forward(raw, version)
            except Exception:
                # Do not expose filesystem paths, bearer tokens, response bodies
                # or exception strings on either of the client protocol streams.
                reply = rpc_error(identity, -32603, 'Local connector request failed')
            if notification:
                continue  # JSON-RPC notifications never receive a response.
            if reply is None:
                reply = rpc_error(identity, -32603, 'Local connector returned no result')
            if (isinstance(message, dict) and message.get('method') == 'initialize'
                    and isinstance(reply.get('result'), dict)):
                version = reply['result'].get('protocolVersion', CURRENT_VERSION)
            send(reply)


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        # argparse normally echoes invalid argument values, including accidental
        # secrets pasted into the command line. Keep CLI failures generic.
        raise ConnectorError(400, 'Invalid command arguments')


def safe_path(value):
    if any(ord(char) < 32 or ord(char) == 127 for char in str(value)):
        raise ConnectorError(400, 'Invalid private path')
    return outside(value)


def config_text(workspace):
    # TOML basic strings accept these JSON string escapes for ordinary absolute
    # paths. Paths cannot contain control characters (checked by safe_path).
    # Preserve a virtualenv's interpreter path: resolving its usual symlink
    # would launch the base interpreter without the installed PDF packages.
    strings = [str(Path(sys.executable).absolute()), str(Path(__file__).resolve()),
               'stdio', '--workspace', str(workspace)]
    quoted = [json.dumps(value, ensure_ascii=False) for value in strings]
    return ('# OfferPath local connector; contains paths only, no credentials.\n'
            '[mcp_servers.offerpath]\ncommand = ' + quoted[0] + '\nargs = ['
            + ', '.join(quoted[1:]) + ']\n')


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'stdio', 'config', 'status'])
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--output')
    args = parser.parse_args(argv)
    workspace = safe_path(args.workspace)
    if args.action == 'init':
        init_workspace(workspace)
        print('已创建仓库外的合成私有工作区；没有调用模型API或连接真实账号。')
        return
    if args.action == 'stdio':
        # A normal client exit (EOF), SIGTERM or Ctrl-C owns cleanup; no detached
        # helper process or persistent listening port is left behind.
        def stop(_signum, _frame):
            raise KeyboardInterrupt()
        previous = signal.signal(signal.SIGTERM, stop)
        try:
            run_stdio(workspace)
        finally:
            signal.signal(signal.SIGTERM, previous)
        return
    # Validate initialized private state without binding a review port.
    service = QwenService(workspace)
    try:
        if args.action == 'config':
            if not args.output:
                raise ConnectorError(400, 'A new private output file is required')
            output = safe_path(args.output)
            if output.exists() or not output.parent.is_dir():
                raise ConnectorError(400, 'Output exists or parent is missing')
            descriptor = os.open(str(output), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                stream.write(config_text(workspace))
            print('已生成仅含本机路径的Codex配置片段；尚未修改Codex全局配置。')
        else:
            state = service.state()
            print(json.dumps(dict(mode=service.config['mode'], packages=len(state['packages']),
                                  records=len(state['records']), transport='stdio',
                                  model_api_calls=0, production_validation=False,
                                  human_pdf_review='local-browser-required'), ensure_ascii=False))
    finally:
        service.db.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except BrokenPipeError:
        # The bridge has already closed. Redirect the abandoned descriptor so
        # Python's final buffered flush cannot emit a traceback or exit 120.
        descriptor = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(descriptor, sys.stdout.fileno())
        finally:
            os.close(descriptor)
    except WorkspaceBusy:
        print('此私有工作区已被另一个Codex连接器使用；请先结束旧连接，或为新任务建立独立工作区。', file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        print('操作未完成；请核对私有工作区、依赖和配置。未输出凭据。', file=sys.stderr)
        raise SystemExit(1)
