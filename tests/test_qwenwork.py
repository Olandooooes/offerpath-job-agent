"""Synthetic-only tests for the Qwen/OfferPath connector and human review gate."""
import copy
import base64
import hashlib
import http.client
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
import urllib.parse
from html.parser import HTMLParser
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('qwenwork', ROOT / 'scripts/qwenwork.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class MetaParser(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.csrf = None
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('name') == 'csrf':
            self.csrf = attrs.get('content')


class FakeOfferPath:
    """In-memory account-specific API; no real credentials or network."""
    synthetic = True

    def __init__(self):
        self.records, self.pdfs, self.puts = {}, {}, []
        self.corrupt_download = False

    def rows(self):
        return copy.deepcopy(list(self.records.values()))

    def request(self, path, method='GET', data=None, headers=None):
        record_id = path.split('/')[3]
        if method == 'PUT':
            self.puts.append(path)
        if path.endswith('/resume'):
            if method == 'PUT':
                current = self.records[record_id]
                if str(current.get('resume_version', 0)) != headers['if-match']:
                    raise ValueError('Synthetic concurrent attachment change')
                self.pdfs[record_id] = data
                current.update(resume_name=urllib.parse.unquote(headers['x-resume-name']),
                               resume_version=current.get('resume_version', 0) + 1)
                return b'{}'
            return b'%PDF-corrupted-download' if self.corrupt_download else self.pdfs[record_id]
        if method == 'PUT':
            record = json.loads(data)
            record.setdefault('resume_version', 0)
            self.records[record_id] = record
        return b'{}'


class QwenworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'synthetic-private'
        self.config = m.init_workspace(self.root)
        self.secrets = json.loads((self.root / 'secrets.json').read_text())
        self.service = m.QwenService(self.root, base_url='http://127.0.0.1:4327')
        self.principal = self.service.authenticate(self.secrets['bridge_token'])
        self.cookies = {}
        self.csrf = None

    def tearDown(self):
        for service in (self.service, getattr(self, 'other_service', None)):
            db = getattr(service, 'db', None)
            if db is not None:
                db.close()
        self.temp.cleanup()

    def tool(self, name, arguments=None):
        return self.service.call_tool(self.principal, name, arguments or {})

    def context(self, job_id='demo-integration', fact_ids=None):
        args = {'job_id': job_id}
        if fact_ids is not None:
            args['fact_ids'] = fact_ids
        return self.tool('get_context', args)

    @staticmethod
    def text(fact):
        details = fact['details']
        return '；'.join(details) if isinstance(details, list) else details

    def draft_arguments(self, context):
        known = {f['id']: f for f in context['facts']}
        # Deliberately different, manually authored synthetic client outputs.
        # An unsupported requirement remains a gap rather than a fabricated fit.
        preferred = (['fact-2'] if context['job']['id'] == 'demo-product'
                     else ['fact-1', 'fact-3'])
        facts = [known[i] for i in preferred if i in known] or context['facts'][:1]
        requirements = context['job']['requirements']
        references = (['fact-2', 'fact-2', None] if context['job']['id'] == 'demo-product'
                      else ['fact-1', 'fact-1', 'fact-3', None])
        used = {f['id'] for f in facts}
        return {
            'context_id': context['context_id'],
            'summary': {'text': self.text(facts[0]), 'fact_ids': [facts[0]['id']]},
            'items': [{'fact_id': f['id'], 'title': f['title'], 'text': self.text(f)} for f in facts],
            'mapping': [{'requirement_index': i, 'fact_id': references[i] if references[i] in used else None}
                        for i in range(len(requirements))],
            'changes': ['SYNTHETIC: selected and ordered confirmed experience for this job'],
        }

    def draft(self, job_id='demo-integration'):
        return self.tool('save_draft', self.draft_arguments(self.context(job_id)))

    def http(self, method, path, payload=None, extra=None):
        headers = {'Origin': 'http://127.0.0.1:4327'}
        if self.cookies:
            headers['Cookie'] = '; '.join(k + '=' + v for k, v in self.cookies.items())
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        headers.update(extra or {})
        body = b'' if payload is None else json.dumps(payload).encode()
        try:
            status, kind, response, extras = self.service.handle_http(method, path, headers, body)
        except m.ConnectorError as exc:
            status, response, extras = exc.status, json.dumps({'error': exc.message}).encode(), {}
        for key, value in (extras.items() if isinstance(extras, dict) else extras):
            if key.lower() == 'set-cookie':
                cookie = SimpleCookie()
                cookie.load(value)
                self.cookies.update({name: item.value for name, item in cookie.items()})
        return status, response

    def login(self):
        status, page = self.http('GET', '/')
        self.assertEqual(status, 200)
        csrf = MetaParser(page.decode()).csrf
        self.assertTrue(csrf, 'Local login page must expose a session-bound CSRF value')
        status, response = self.http('POST', '/session', {'code': self.secrets['review_code'], 'csrf': csrf})
        self.assertEqual(status, 200, response.decode())
        status, response = self.http('GET', '/state')
        self.assertEqual(status, 200)
        state = json.loads(response)
        self.csrf = state['csrf']
        return state

    def approve(self, package):
        if not self.csrf:
            self.login()
        status, response = self.http('GET', '/review?id=' + package['package_id'])
        self.assertEqual(status, 200)
        status, pdf = self.http('GET', '/pdf/' + package['package_id'])
        self.assertEqual(status, 200)
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertEqual(hashlib.sha256(pdf).hexdigest(), package['sha256'])
        status, response = self.http('POST', '/approve', {
            'package_id': package['package_id'], 'version': package['version'],
            'sha256': package['sha256'], 'csrf': self.csrf,
        })
        self.assertEqual(status, 200, response.decode())
        return pdf

    def report(self, package, outcome='user_reported'):
        return self.tool('report_application', {
            'package_id': package['package_id'], 'outcome': outcome,
            'same_attachment': True, 'receipt': 'SYNTHETIC user report only; no recruiter contacted',
        })

    def test_workspace_is_private_non_destructive_and_has_no_tokens_in_safe_config(self):
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        for name in ('config.json', 'profile.json', 'jobs.json', 'secrets.json'):
            self.assertEqual((self.root / name).stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.secrets['bridge_token'] in json.dumps(self.config))
        self.assertFalse(self.secrets['review_code'] in json.dumps(self.config))
        if (self.root / 'db.sqlite3').exists():
            self.assertEqual((self.root / 'db.sqlite3').stat().st_mode & 0o777, 0o600)
        self.assertIsNone(self.secrets['offerpath_token'])
        before = (self.root / 'secrets.json').read_bytes()
        with self.assertRaises(m.ConnectorError):
            m.init_workspace(self.root)
        self.assertEqual(before, (self.root / 'secrets.json').read_bytes())
        with patch('socket.socket', side_effect=AssertionError('No external connections')):
            m.init_workspace(Path(self.temp.name) / 'offline-second')

    def test_repository_and_symlink_workspace_are_rejected(self):
        with self.assertRaises(m.ConnectorError):
            m.init_workspace(ROOT / 'forbidden-private-test')
        link = Path(self.temp.name) / 'repository-link'
        link.symlink_to(ROOT, target_is_directory=True)
        with self.assertRaises(m.ConnectorError):
            m.init_workspace(link / 'forbidden-private-test')

    def test_token_auth_and_account_isolation(self):
        with self.assertRaises(Exception):
            self.service.authenticate('not-a-valid-token')
        second = Path(self.temp.name) / 'second-account'
        m.init_workspace(second)
        self.other_service = m.QwenService(second, base_url='http://127.0.0.1:4328')
        other_secrets = json.loads((second / 'secrets.json').read_text())
        other_principal = self.other_service.authenticate(other_secrets['bridge_token'])
        self.assertNotEqual(self.principal, other_principal)
        with self.assertRaises(Exception):
            self.other_service.authenticate(self.secrets['bridge_token'])
        with self.assertRaises(Exception):
            self.other_service.call_tool(other_principal, 'get_pdf', {'package_id': self.draft()['package_id']})

    def test_tools_do_not_expose_approval_or_submission(self):
        names = [tool['name'] for tool in self.service.list_tools()]
        self.assertIn('get_context', names)
        self.assertIn('save_draft', names)
        self.assertIn('sync_records', names)
        self.assertNotIn('approve', names)
        self.assertNotIn('submit_application', names)
        with self.assertRaises(Exception):
            self.tool('approve', {'approved': True})

    def test_context_can_only_select_existing_confirmed_facts(self):
        context = self.context()
        chosen = context['facts'][0]['id']
        selected = self.context(fact_ids=[chosen])
        self.assertEqual([f['id'] for f in selected['facts']], [chosen])
        self.assertNotEqual(context['context_id'], selected['context_id'])
        with self.assertRaises(Exception):
            self.context(fact_ids=['invented-fact'])
        with self.assertRaises(Exception):
            self.context(job_id='missing-job')

    def test_ai_proposed_profile_waits_for_human_exact_version_confirmation(self):
        package = self.draft()
        self.approve(package)
        original = json.loads((self.root / 'profile.json').read_text())
        args = {key: copy.deepcopy(original[key]) for key in
                ('name', 'education', 'skills', 'synthetic', 'facts')}
        args['skills'] += '、合成资料补充'
        proposal = self.tool('propose_profile', args)
        self.assertFalse(proposal['confirmed'])
        self.assertEqual(proposal['version'], original['version'] + 1)
        with self.assertRaises(m.ConnectorError):
            self.context()
        before = (self.root / 'profile.json').read_bytes()
        for forbidden in ('confirmed', 'approved', 'approve'):
            with self.assertRaises(m.ConnectorError):
                self.tool('propose_profile', dict(args, **{forbidden: True}))
        self.assertEqual(before, (self.root / 'profile.json').read_bytes())
        status, response = self.http('GET', '/state')
        self.assertEqual(status, 200)
        shown = json.loads(response)
        self.assertEqual(shown['profile']['facts'], args['facts'])
        self.assertFalse(shown['profile']['confirmed'])
        old_package = next(p for p in shown['packages'] if p['package_id'] == package['package_id'])
        self.assertFalse(old_package['approved'])
        # A second extraction invalidates a confirmation based on the first
        # displayed version, even if the AI repeats most of the same facts.
        args['skills'] += '、第二次合成补充'
        newer = self.tool('propose_profile', args)
        for payload, headers in (
            ({'version': proposal['version'], 'csrf': self.csrf}, {}),
            ({'version': newer['version'], 'csrf': 'wrong'}, {}),
            ({'version': newer['version'], 'csrf': self.csrf}, {}),
            ({'version': newer['version'], 'csrf': self.csrf},
             {'Authorization': 'Bearer ' + self.secrets['bridge_token']}),
        ):
            status, _ = self.http('POST', '/profile-confirm', payload, headers)
            self.assertGreaterEqual(status, 400)
        with self.assertRaises(m.ConnectorError):
            self.context()
        status, response = self.http('GET', '/state')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(response)['profile']['version'], newer['version'])
        status, response = self.http('POST', '/profile-confirm', {
            'version': newer['version'], 'csrf': self.csrf,
        })
        self.assertEqual(status, 200, response.decode())
        self.assertEqual(self.context()['facts'], args['facts'])

    def test_saved_jobs_are_versioned_separately_and_unknown_lock_cannot_be_reset(self):
        job = self.tool('list_jobs')['jobs'][0]
        args = {key: copy.deepcopy(job[key]) for key in
                ('company', 'role', 'location', 'url', 'jd', 'requirements', 'synthetic')}
        args.update(company='Synthetic Connector Studio', url='https://example.test/jobs/custom-integration')
        first = self.tool('save_job', args)
        self.assertEqual(first['version'], 1)
        self.assertEqual(first['jd'], args['jd'])
        context = self.context(first['id'])
        second_args = dict(args, company='Another Synthetic Studio',
                           url='https://example.test/jobs/custom-other')
        second = self.tool('save_job', second_args)
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(second['version'], 1)
        args['jd'] += ' 本次更新进一步说明合成岗位的接口可靠性要求。'
        updated = self.tool('save_job', args)
        self.assertEqual(updated['id'], first['id'])
        self.assertEqual(updated['version'], 2)
        with self.assertRaises(m.ConnectorError):
            self.tool('save_draft', self.draft_arguments(context))
        with self.assertRaises(m.ConnectorError):
            self.tool('save_job', dict(args, approved=True))
        package = self.draft(first['id'])
        self.approve(package)
        self.report(package, 'unknown')
        for changed in (args, dict(args, url='https://example.test/jobs/changed-url'),
                        dict(args, company=args['company'].upper())):
            with self.assertRaises(m.ConnectorError):
                self.tool('save_job', changed)
        saved = {j['id']: j for j in self.tool('list_jobs')['jobs']}
        self.assertEqual(saved[first['id']]['version'], 2)
        self.assertEqual(saved[second['id']]['version'], 1)

    def test_saved_job_cannot_alias_a_locked_synthetic_seed_job(self):
        package = self.draft()
        self.approve(package)
        self.report(package, 'unknown')
        job = next(j for j in self.tool('list_jobs')['jobs'] if j['id'] == 'demo-integration')
        args = {key: copy.deepcopy(job[key]) for key in
                ('company', 'role', 'location', 'url', 'jd', 'requirements', 'synthetic')}
        with self.assertRaises(m.ConnectorError):
            self.tool('save_job', args)
        self.assertEqual(len(self.tool('list_jobs')['jobs']), 2)

    def test_draft_rejects_unknown_or_out_of_scope_fact_and_false_approval(self):
        context = self.context()
        payload = self.draft_arguments(context)
        payload['summary']['fact_ids'] = ['invented-fact']
        with self.assertRaises(Exception):
            self.tool('save_draft', payload)
        selected = self.context(fact_ids=[context['facts'][0]['id']])
        payload = self.draft_arguments(selected)
        payload['items'].append({'fact_id': context['facts'][-1]['id'], 'title': 'Foreign fact', 'text': 'Foreign fact'})
        with self.assertRaises(Exception):
            self.tool('save_draft', payload)
        payload = self.draft_arguments(context)
        payload['approved'] = True
        try:
            package = self.tool('save_draft', payload)
        except Exception:
            return
        self.assertFalse(package['approved'])
        with self.assertRaises(Exception):
            self.report(package)

    def test_mapping_indices_and_invented_numbers_are_rejected(self):
        context = self.context()
        for mutate in (
            lambda p: p['mapping'].append(copy.deepcopy(p['mapping'][0])),
            lambda p: p['mapping'].__setitem__(0, {'requirement_index': 9999, 'fact_id': None}),
            lambda p: p['summary'].__setitem__('text', self.text(context['facts'][0]) + ' Increased revenue 987654321 percent.'),
        ):
            payload = self.draft_arguments(context)
            mutate(payload)
            with self.assertRaises(Exception):
                self.tool('save_draft', payload)

    def test_two_jobs_have_distinct_bound_pdf_and_unapproved_drafts(self):
        first, second = self.draft(), self.draft('demo-product')
        self.assertFalse(first['approved'])
        self.assertFalse(second['approved'])
        self.assertNotEqual(first['package_id'], second['package_id'])
        self.assertNotEqual(first['sha256'], second['sha256'])
        self.assertIn('/review', first['review_url'])
        self.assertIn('/pdf/', first['pdf_url'])
        for url in (first['review_url'], first['pdf_url']):
            self.assertFalse(self.secrets['bridge_token'] in url)
            self.assertFalse(self.secrets['review_code'] in url)
        info = self.tool('get_pdf', {'package_id': first['package_id']})
        self.assertEqual(info['sha256'], first['sha256'])
        with self.assertRaises(Exception):
            self.report(first)
        with self.assertRaises(Exception):
            self.tool('sync_records', {'package_id': first['package_id']})

    def test_changed_private_profile_or_job_invalidates_old_context_and_approval(self):
        context = self.context()
        profile_path = self.root / 'profile.json'
        profile = json.loads(profile_path.read_text())
        profile['skills'] += '、合成补充技能'
        profile_path.write_text(json.dumps(profile, ensure_ascii=False))
        with self.assertRaises(m.ConnectorError):
            self.tool('save_draft', self.draft_arguments(context))
        package = self.draft()
        self.approve(package)
        jobs_path = self.root / 'jobs.json'
        jobs = json.loads(jobs_path.read_text())
        jobs[0]['jd'] += ' 合成岗位要求更新。'
        jobs_path.write_text(json.dumps(jobs, ensure_ascii=False))
        with self.assertRaises(m.ConnectorError):
            self.report(package)
        historical = self.tool('get_pdf', {'package_id': package['package_id']})
        self.assertFalse(historical['approved'])
        self.assertFalse(historical['current'])

    def test_new_draft_revokes_previous_approval_but_keeps_original_pdf(self):
        context = self.context()
        args = self.draft_arguments(context)
        first = self.tool('save_draft', args)
        original = self.approve(first)
        args['summary']['text'] += ' 本版聚焦已确认的接口与数据处理经历。'
        second = self.tool('save_draft', args)
        self.assertFalse(second['approved'])
        self.assertGreater(second['version'], first['version'])
        old = self.tool('get_pdf', {'package_id': first['package_id']})
        self.assertFalse(old['approved'])
        self.assertTrue(old['superseded'])
        status, retained = self.http('GET', '/pdf/' + first['package_id'])
        self.assertEqual(status, 200)
        self.assertEqual(retained, original)
        with self.assertRaises(m.ConnectorError):
            self.report(first)
        status, _ = self.http('POST', '/approve', {
            'package_id': first['package_id'], 'version': first['version'],
            'sha256': first['sha256'], 'csrf': self.csrf,
        })
        self.assertGreaterEqual(status, 400)

    def test_browser_approval_requires_login_csrf_exact_hash_and_actual_pdf(self):
        package = self.draft()
        status, _ = self.http('GET', '/pdf/' + package['package_id'])
        self.assertGreaterEqual(status, 400, 'PDF must not be anonymously available')
        status, _ = self.http('POST', '/approve', {
            'package_id': package['package_id'], 'version': package['version'],
            'sha256': package['sha256'], 'csrf': 'fake',
        })
        self.assertGreaterEqual(status, 400)
        self.login()
        payload = {'package_id': package['package_id'], 'version': package['version'],
                   'sha256': package['sha256'], 'csrf': self.csrf}
        status, _ = self.http('POST', '/approve', payload)
        self.assertGreaterEqual(status, 400, 'Review link alone must not count as viewing the PDF')
        self.http('GET', '/pdf/' + package['package_id'])
        for changed in ({'csrf': 'wrong'}, {'sha256': '0' * 64}, {'version': package['version'] + 1}):
            bad = dict(payload, **changed)
            status, _ = self.http('POST', '/approve', bad)
            self.assertGreaterEqual(status, 400)
        status, _ = self.http('POST', '/approve', payload,
                              {'Authorization': 'Bearer ' + self.secrets['bridge_token']})
        self.assertGreaterEqual(status, 400, 'AI bearer token cannot share the human approval route')
        self.approve(package)
        info = self.tool('get_pdf', {'package_id': package['package_id']})
        self.assertTrue(info['approved'])

    def test_ai_resource_contains_exact_bytes_but_cannot_count_as_human_pdf_review(self):
        package = self.draft()
        self.login()
        resource = self.service.read_resource(self.principal, package['resource_uri'])
        self.assertEqual(resource['contents'][0]['mimeType'], 'application/pdf')
        data = base64.b64decode(resource['contents'][0]['blob'])
        self.assertEqual(hashlib.sha256(data).hexdigest(), package['sha256'])
        status, _ = self.http('POST', '/approve', {
            'package_id': package['package_id'], 'version': package['version'],
            'sha256': package['sha256'], 'csrf': self.csrf,
        })
        self.assertGreaterEqual(status, 400, 'A tool resource fetch is not human approval')
        self.assertEqual(self.approve(package), data)

    def test_pdf_storage_change_after_viewing_cannot_be_approved(self):
        package = self.draft()
        self.login()
        status, _ = self.http('GET', '/pdf/' + package['package_id'])
        self.assertEqual(status, 200)
        self.service.db.execute('UPDATE pdfs SET value=? WHERE id=?',
                                (b'%PDF-SYNTHETIC-corruption', package['package_id']))
        self.service.db.commit()
        status, _ = self.http('POST', '/approve', {
            'package_id': package['package_id'], 'version': package['version'],
            'sha256': package['sha256'], 'csrf': self.csrf,
        })
        self.assertGreaterEqual(status, 400)
        _, response = self.http('GET', '/state')
        actual = next(p for p in json.loads(response)['packages'] if p['package_id'] == package['package_id'])
        self.assertFalse(actual['approved'])

    def test_changing_connection_cannot_reuse_context_approval_sync_or_archive(self):
        self.login()
        old_context = self.context()
        old_package = self.tool('save_draft', self.draft_arguments(old_context))
        status, _ = self.http('GET', '/pdf/' + old_package['package_id'])
        self.assertEqual(status, 200)
        first_remote, second_remote = FakeOfferPath(), FakeOfferPath()
        first_remote.base = 'https://first-account.example.test'
        second_remote.base = 'https://second-account.example.test'
        with patch('qwen_remote.RemoteOfferPath', side_effect=[first_remote, second_remote]):
            status, response = self.http('POST', '/connection', {
                'base_url': first_remote.base, 'token': 'synthetic-first-account-token', 'csrf': self.csrf,
            })
            self.assertEqual(status, 200, response.decode())
            self.assertEqual(json.loads(response)['writes'], 0)
            with self.assertRaises(m.ConnectorError):
                self.tool('save_draft', self.draft_arguments(old_context))
            status, _ = self.http('POST', '/approve', {
                'package_id': old_package['package_id'], 'version': old_package['version'],
                'sha256': old_package['sha256'], 'csrf': self.csrf,
            })
            self.assertGreaterEqual(status, 400)
            package = self.draft()
            pdf = self.approve(package)
            self.report(package)
            record = self.tool('sync_records', {'package_id': package['package_id']})
            self.assertEqual(record['state'], 'bytes_verified')
            status, archived = self.http('GET', '/archive/' + package['package_id'])
            self.assertEqual(status, 200)
            self.assertEqual(archived, pdf)
            writes_before_switch = list(first_remote.puts)
            status, response = self.http('POST', '/connection', {
                'base_url': second_remote.base, 'token': 'synthetic-second-account-token', 'csrf': self.csrf,
            })
            self.assertEqual(status, 200, response.decode())
            self.assertEqual(json.loads(response)['writes'], 0)
            with self.assertRaises(m.ConnectorError):
                self.tool('sync_records', {'package_id': package['package_id']})
            status, _ = self.http('GET', '/archive/' + package['package_id'])
            self.assertGreaterEqual(status, 400)
            status, _ = self.http('POST', '/preview', {'package_id': package['package_id'], 'csrf': self.csrf})
            self.assertGreaterEqual(status, 400)
            status, response = self.http('GET', '/state')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(response)['records'], [])
            self.assertEqual(first_remote.puts, writes_before_switch)
            self.assertEqual(second_remote.puts, [])
            self.assertEqual(second_remote.records, {})

    def test_reported_snapshot_can_finish_sync_after_profile_changes(self):
        package = self.draft()
        pdf = self.approve(package)
        report = self.report(package)
        original = json.loads((self.root / 'profile.json').read_text())
        args = {key: copy.deepcopy(original[key]) for key in
                ('name', 'education', 'skills', 'synthetic', 'facts')}
        args['name'] = '另一版合成资料（虚构）'
        args['facts'][0]['details'] += ' 这条合成补充尚未由本人确认。'
        self.tool('propose_profile', args)
        with self.assertRaises(m.ConnectorError):
            self.context()
        first = self.tool('sync_records', {'package_id': package['package_id']})
        self.assertEqual(first['state'], 'bytes_verified')
        self.assertEqual(first['sha256'], package['sha256'])
        self.assertEqual(first['receipt'], report['receipt'])
        status, archived = self.http('GET', '/archive/' + package['package_id'])
        self.assertEqual(status, 200)
        self.assertEqual(archived, pdf)
        status, response = self.http('POST', '/preview', {'package_id': package['package_id'], 'csrf': self.csrf})
        self.assertEqual(status, 200, response.decode())
        final = self.tool('sync_records', {'package_id': package['package_id']})
        self.assertEqual(final['state'], 'complete')
        self.assertEqual(len(self.tool('list_records')['records']), 1)
        self.assertFalse(json.loads((self.root / 'profile.json').read_text())['confirmed'])

    def test_explicit_human_recovery_rebinds_only_an_incomplete_reported_snapshot(self):
        self.login()
        first_remote, second_remote = FakeOfferPath(), FakeOfferPath()
        first_remote.base = 'https://recovery-first.example.test'
        second_remote.base = 'https://recovery-second.example.test'
        with patch('qwen_remote.RemoteOfferPath', side_effect=[first_remote, second_remote]):
            status, _ = self.http('POST', '/connection', {
                'base_url': first_remote.base, 'token': 'synthetic-recovery-first', 'csrf': self.csrf,
            })
            self.assertEqual(status, 200)
            package = self.draft()
            pdf = self.approve(package)
            report = self.report(package)
            initial = self.tool('sync_records', {'package_id': package['package_id']})
            self.assertEqual(initial['state'], 'bytes_verified')
            unknown = self.draft('demo-product')
            self.approve(unknown)
            self.report(unknown, 'unknown')
            # A separate already-complete application must not become a way to
            # copy a finished record to another account through recovery.
            seed = self.tool('list_jobs')['jobs'][0]
            job_args = {key: copy.deepcopy(seed[key]) for key in
                        ('company', 'role', 'location', 'url', 'jd', 'requirements', 'synthetic')}
            job_args.update(company='Synthetic Finished Application', url='https://example.test/jobs/finished')
            finished_job = self.tool('save_job', job_args)
            finished = self.draft(finished_job['id'])
            self.approve(finished)
            self.report(finished)
            self.tool('sync_records', {'package_id': finished['package_id']})
            self.http('GET', '/archive/' + finished['package_id'])
            status, _ = self.http('POST', '/preview', {'package_id': finished['package_id'], 'csrf': self.csrf})
            self.assertEqual(status, 200)
            writes_before_switch = list(first_remote.puts)
            status, _ = self.http('POST', '/connection', {
                'base_url': second_remote.base, 'token': 'synthetic-recovery-second', 'csrf': self.csrf,
            })
            self.assertEqual(status, 200)
            with self.assertRaises(m.ConnectorError):
                self.tool('sync_records', {'package_id': package['package_id']})
            status, response = self.http('GET', '/state')
            self.assertEqual(status, 200)
            current = json.loads(response)
            self.csrf = current['csrf']
            self.assertNotEqual(current['connection_id'], package['connection_id'])
            recovery = {
                'package_id': package['package_id'], 'version': package['version'],
                'sha256': package['sha256'], 'connection_id': current['connection_id'], 'csrf': self.csrf,
            }
            status, _ = self.http('POST', '/rebind', recovery)
            self.assertGreaterEqual(status, 400, 'Previous-account PDF viewing must not authorize a new destination')
            status, actual = self.http('GET', '/pdf/' + package['package_id'])
            self.assertEqual(status, 200)
            self.assertEqual(actual, pdf)
            for changed, headers in (
                ({'sha256': '0' * 64}, {}),
                ({'version': package['version'] + 1}, {}),
                ({'connection_id': package['connection_id']}, {}),
                ({'csrf': 'wrong'}, {}),
                ({}, {'Authorization': 'Bearer ' + self.secrets['bridge_token']}),
            ):
                status, _ = self.http('POST', '/rebind', dict(recovery, **changed), headers)
                self.assertGreaterEqual(status, 400)
            for prohibited in (unknown, finished):
                self.http('GET', '/pdf/' + prohibited['package_id'])
                status, _ = self.http('POST', '/rebind', dict(recovery,
                    package_id=prohibited['package_id'], version=prohibited['version'], sha256=prohibited['sha256']))
                self.assertGreaterEqual(status, 400, 'Unknown and completed applications cannot be rebound')
            # This is still an in-memory adapter; toggling its declared mode
            # verifies that synthetic material cannot be recovered to a real API.
            second_remote.synthetic = False
            status, _ = self.http('POST', '/rebind', recovery)
            self.assertGreaterEqual(status, 400)
            second_remote.synthetic = True
            status, response = self.http('POST', '/rebind', recovery)
            self.assertEqual(status, 200, response.decode())
            self.assertEqual(self.report(package), report)
            with self.assertRaises(m.ConnectorError):
                self.context()
            restored = self.tool('sync_records', {'package_id': package['package_id']})
            self.assertEqual(restored['state'], 'bytes_verified')
            self.assertEqual(restored['sha256'], package['sha256'])
            self.assertEqual(restored['connection_id'], current['connection_id'])
            self.assertEqual(first_remote.puts, writes_before_switch)
            self.assertEqual(len(second_remote.records), 1)
            history = self.service.state()['history_records']
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]['package_id'], package['package_id'])
            self.assertEqual(history[0]['connection_id'], package['connection_id'])
            self.assertEqual(history[0]['state'], 'bytes_verified')
            status, _ = self.http('POST', '/preview', {'package_id': package['package_id'], 'csrf': self.csrf})
            self.assertGreaterEqual(status, 400, 'Recovery must not inherit archive preview from the old connection')
            status, archived = self.http('GET', '/archive/' + package['package_id'])
            self.assertEqual(status, 200)
            self.assertEqual(archived, pdf)
            status, _ = self.http('POST', '/preview', {'package_id': package['package_id'], 'csrf': self.csrf})
            self.assertEqual(status, 200)
            self.assertEqual(self.tool('sync_records', {'package_id': package['package_id']})['state'], 'complete')
            status, _ = self.http('POST', '/rebind', recovery)
            self.assertGreaterEqual(status, 400)

    def test_failed_png_render_does_not_count_as_draft_or_archive_review(self):
        package = self.draft()
        self.login()
        with patch('qwen_pdf.render_pdf', side_effect=ValueError('Synthetic renderer failure')):
            with self.assertRaises(ValueError):
                self.http('GET', '/pdf/' + package['package_id'] + '/preview.png')
        status, _ = self.http('POST', '/approve', {
            'package_id': package['package_id'], 'version': package['version'],
            'sha256': package['sha256'], 'csrf': self.csrf,
        })
        self.assertGreaterEqual(status, 400)
        self.approve(package)  # Reading the actual PDF remains a valid fallback.
        self.report(package)
        self.tool('sync_records', {'package_id': package['package_id']})
        with patch('qwen_pdf.render_pdf', side_effect=ValueError('Synthetic renderer failure')):
            with self.assertRaises(ValueError):
                self.http('GET', '/archive/' + package['package_id'] + '/preview.png')
        status, _ = self.http('POST', '/preview', {'package_id': package['package_id'], 'csrf': self.csrf})
        self.assertGreaterEqual(status, 400)
        status, _ = self.http('GET', '/archive/' + package['package_id'])
        self.assertEqual(status, 200)
        status, response = self.http('POST', '/preview', {'package_id': package['package_id'], 'csrf': self.csrf})
        self.assertEqual(status, 200, response.decode())

    def test_real_http_mcp_and_human_review_complete_synthetic_flow(self):
        # This is an actual loopback wire test of the real service, not the
        # transport's FakeService. It never authenticates to a third-party AI.
        server = ThreadingHTTPServer(('127.0.0.1', 0), m.make_handler(self.service, 'http://127.0.0.1:1'))
        origin = 'http://127.0.0.1:' + str(server.server_port)
        self.service.base_url = origin
        server.RequestHandlerClass = m.make_handler(self.service, origin)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        cookies, request_number = {}, 0

        def request(method, path, payload=None, bearer=False):
            headers = {}
            if bearer:
                headers['Authorization'] = 'Bearer ' + self.secrets['bridge_token']
            if cookies:
                headers['Cookie'] = '; '.join(k + '=' + v for k, v in cookies.items())
            if payload is not None:
                headers['Content-Type'] = 'application/json'
                if path != '/mcp':
                    headers['Origin'] = origin
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
            try:
                connection.request(method, path, body=None if payload is None else json.dumps(payload).encode(), headers=headers)
                response = connection.getresponse()
                status, data = response.status, response.read()
                for key, value in response.getheaders():
                    if key.lower() == 'set-cookie':
                        parsed = SimpleCookie()
                        parsed.load(value)
                        cookies.update({k: v.value for k, v in parsed.items()})
            finally:
                connection.close()
            self.assertEqual(status, 200, data.decode(errors='replace')[:250] if status != 200 else '')
            return data

        def rpc(method, params=None):
            nonlocal request_number
            request_number += 1
            value = json.loads(request('POST', '/mcp', {
                'jsonrpc': '2.0', 'id': request_number, 'method': method, 'params': params or {},
            }, bearer=True))
            self.assertNotIn('error', value)
            return value['result']

        def tool(name, args=None):
            result = rpc('tools/call', {'name': name, 'arguments': args or {}})
            self.assertFalse(result.get('isError'), result['content'][0]['text'])
            return json.loads(result['content'][0]['text'])

        try:
            initialized = rpc('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
                                              'clientInfo': {'name': 'synthetic-wire-test', 'version': '1'}})
            self.assertIn('tools', initialized['capabilities'])
            self.assertEqual(len(tool('list_jobs')['jobs']), 2)
            context = tool('get_context', {'job_id': 'demo-integration'})
            package = tool('save_draft', self.draft_arguments(context))
            resource = rpc('resources/read', {'uri': package['resource_uri']})
            resource_pdf = base64.b64decode(resource['contents'][0]['blob'])
            page = request('GET', '/').decode()
            csrf = MetaParser(page).csrf
            request('POST', '/session', {'code': self.secrets['review_code'], 'csrf': csrf})
            request('GET', '/review?id=' + package['package_id'])
            pdf = request('GET', '/pdf/' + package['package_id'])
            self.assertEqual(pdf, resource_pdf)
            self.assertEqual(hashlib.sha256(pdf).hexdigest(), package['sha256'])
            request('POST', '/approve', {'package_id': package['package_id'], 'version': package['version'],
                                         'sha256': package['sha256'], 'csrf': csrf})
            tool('report_application', {'package_id': package['package_id'], 'outcome': 'user_reported',
                                        'same_attachment': True, 'receipt': 'SYNTHETIC local wire test only'})
            first = tool('sync_records', {'package_id': package['package_id']})
            self.assertEqual(first['state'], 'bytes_verified')
            self.assertEqual(request('GET', '/archive/' + package['package_id']), pdf)
            request('POST', '/preview', {'package_id': package['package_id'], 'csrf': csrf})
            final = tool('sync_records', {'package_id': package['package_id']})
            self.assertEqual(final['state'], 'complete')
            records = tool('list_records')['records']
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['outcome'], 'user_reported')
            self.assertFalse(records[0]['external_verified'])
            self.assertTrue(records[0]['synthetic'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_user_report_and_sync_are_idempotent_and_need_archive_preview(self):
        package = self.draft()
        pdf = self.approve(package)
        with self.assertRaises(Exception):
            self.tool('report_application', {
                'package_id': package['package_id'], 'outcome': 'user_reported',
                'same_attachment': False, 'receipt': 'SYNTHETIC mismatched attachment',
            })
        self.report(package)
        first = self.tool('sync_records', {'package_id': package['package_id']})
        self.assertNotEqual(first['state'], 'complete')
        self.assertEqual(first['state'], 'bytes_verified')
        self.assertEqual(first['sha256'], hashlib.sha256(pdf).hexdigest())
        second = self.tool('sync_records', {'package_id': package['package_id']})
        self.assertEqual(first['record_id'], second['record_id'])
        records = self.tool('list_records')['records']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['outcome'], 'user_reported')
        status, response = self.http('POST', '/preview', {'package_id': package['package_id'], 'csrf': self.csrf})
        self.assertGreaterEqual(status, 400, 'Draft PDF preview cannot count as archive preview')
        status, archived = self.http('GET', '/archive/' + package['package_id'])
        self.assertEqual(status, 200)
        self.assertEqual(archived, pdf)
        status, response = self.http('POST', '/preview', {'package_id': package['package_id'], 'csrf': self.csrf})
        self.assertEqual(status, 200, response.decode())
        final = self.tool('sync_records', {'package_id': package['package_id']})
        self.assertEqual(final['state'], 'complete')
        self.assertEqual(len(self.tool('list_records')['records']), 1)

    def test_unknown_outcome_stays_locked_after_restart(self):
        package = self.draft()
        self.approve(package)
        self.report(package, 'unknown')
        for operation in (
            lambda: self.report(package),
            lambda: self.tool('sync_records', {'package_id': package['package_id']}),
            lambda: self.draft(),
        ):
            with self.assertRaises(Exception):
                operation()
        db = getattr(self.service, 'db', None)
        if db is not None:
            db.close()
        self.service = m.QwenService(self.root, base_url='http://127.0.0.1:4327')
        self.principal = self.service.authenticate(self.secrets['bridge_token'])
        with self.assertRaises(Exception):
            self.report(package)
        with self.assertRaises(Exception):
            self.draft()
        self.assertEqual(self.tool('list_records')['records'], [])

    def test_sync_download_corruption_is_not_complete_and_retry_does_not_duplicate(self):
        remote = FakeOfferPath()
        db = getattr(self.service, 'db', None)
        if db is not None:
            db.close()
        self.service = m.QwenService(self.root, base_url='http://127.0.0.1:4327', remote=remote)
        self.principal = self.service.authenticate(self.secrets['bridge_token'])
        package = self.draft()
        pdf = self.approve(package)
        self.report(package)
        remote.corrupt_download = True
        with self.assertRaises(Exception):
            self.tool('sync_records', {'package_id': package['package_id']})
        self.assertEqual(len(remote.records), 1)
        remote.corrupt_download = False
        result = self.tool('sync_records', {'package_id': package['package_id']})
        self.assertEqual(result['state'], 'bytes_verified')
        record_id = result['record_id']
        self.assertEqual(remote.pdfs[record_id], pdf)
        remote.records[record_id].update(stage='面试', notes='User-maintained synthetic note')
        self.tool('sync_records', {'package_id': package['package_id']})
        self.assertEqual(remote.records[record_id]['stage'], '面试')
        self.assertIn('User-maintained synthetic note', remote.records[record_id]['notes'])
        self.assertEqual(len(remote.records), 1)
        self.assertEqual(remote.puts.count('/api/applications/' + record_id + '/resume'), 1)


if __name__ == '__main__':
    unittest.main()
