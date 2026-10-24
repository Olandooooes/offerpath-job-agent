import copy
import importlib.util
import json
import sqlite3
import tempfile
import unittest
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('agent', Path(__file__).parents[1]/'scripts/agent.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class FakeOfferPath:
    def __init__(self):
        self.records, self.pdfs, self.puts = {}, {}, []
        self.fail_download = False

    def rows(self):
        return copy.deepcopy(list(self.records.values()))

    def request(self, path, method='GET', data=None, headers=None):
        parts = path.split('/')
        record_id = parts[3]
        if method == 'PUT':
            self.puts.append(path)
        if path.endswith('/resume'):
            if method == 'PUT':
                m.require(str(self.records[record_id]['resume_version']) == headers['if-match'], '附件并发冲突')
                self.pdfs[record_id] = data
                self.records[record_id].update(resume_name=m.urllib.parse.unquote(headers['x-resume-name']), resume_version=1)
                return b'{}'
            if self.fail_download:
                raise m.Stop('模拟下载中断')
            return self.pdfs[record_id]
        if method == 'PUT':
            row = json.loads(data)
            row.setdefault('resume_version', 0)
            self.records[record_id] = row
        return b'{}'


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = dict(policy_path=str(self.root/'policy.md'), state_db=str(self.root/'state.sqlite3'), resume_pages=1)
        self.policy = self.file('policy.md', b'fixture policy')
        self.api = FakeOfferPath()
        self.agent = m.Agent(self.config, self.api)
        job = dict(company='Example Company', role='Application Engineer', job_id='job-1', location='Example City', url='https://example.test/jobs/job-1', channel='test', application_id='test-id', verified_at=m.stamp(),
            screening={k:'fixture evidence' for k in ('employer', 'location', 'duties', 'qualifications', 'salary', 'posting_date', 'employment', 'language')},
            jd=self.file('jd.txt', b'fixture complete JD'), base_resume=self.file('base.pdf', b'%PDF-base'), resume=self.file('tailored.pdf', b'%PDF-tailored body'), source=self.file('content.json', b'fixture content'),
            tailoring=dict(substantive_reviewed=True, changes=['fixture substantive change'], mapping=[dict(requirement='APIs', evidence='confirmed integration', fact_source='fixture fact')], diff=self.file('diff.txt', b'fixture diff')),
            visual=dict(passed=True, checked_at=m.stamp(), pages=1, previews=[self.file('preview.png', b'synthetic fixture, never a real visual review')]), form_reviewed=True, requires_user_confirmation=False)
        job['screening']['passed'] = True
        job['visual']['resume_sha256'] = job['resume']['sha256']
        job['selected_attachment_sha256'] = job['resume']['sha256']
        self.package = dict(version=1, batch_id='test-batch', policy_sha256=self.policy['sha256'], authorization=dict(action='apply', user_instruction_ref='synthetic-test-only', max_submissions=1), jobs=[job])
        self.job = job

    def tearDown(self):
        self.agent.db.close()
        self.temp.cleanup()

    def file(self, name, data):
        path = self.root/name
        path.write_bytes(data)
        return dict(path=str(path), sha256=m.sha(data))

    def receipt(self):
        return dict(application_id='test-id', job_id='job-1', resume_sha256=self.job['resume']['sha256'], kind='platform_success', summary='synthetic success', observed_at=m.stamp(), submitted_at=m.stamp(), artifact=self.file('receipt.txt', b'synthetic success fixture'))

    def confirmed(self):
        self.agent.reserve(self.package)
        self.agent.confirm('test-batch', m.key(self.job), 'confirmed', self.receipt())

    def test_generic_renamed_pdf_blocked(self):
        self.job['resume'] = self.file('renamed.pdf', Path(self.job['base_resume']['path']).read_bytes())
        with self.assertRaisesRegex(m.Stop, '通用母版'):
            self.agent.reserve(self.package)
        self.assertEqual(self.agent.status('test-batch'), [])

    def test_no_tailoring_or_visual_blocked(self):
        for field in ('tailoring', 'visual'):
            package = copy.deepcopy(self.package)
            package['jobs'][0][field]['passed' if field == 'visual' else 'substantive_reviewed'] = False
            with self.assertRaises(m.Stop):
                self.agent.check(package)

    def test_resume_modified_after_review_blocked(self):
        Path(self.job['resume']['path']).write_bytes(b'%PDF-replaced')
        with self.assertRaisesRegex(m.Stop, '哈希'):
            self.agent.reserve(self.package)

    def test_policy_modified_blocked(self):
        Path(self.config['policy_path']).write_text('new rules')
        with self.assertRaises(m.Stop):
            self.agent.check(self.package)

    def test_stale_jd_blocked(self):
        self.job['verified_at'] = '2000-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(m.Stop, '过期'):
            self.agent.check(self.package)

    def test_unknown_lock_survives_restart_no_sync(self):
        self.agent.reserve(self.package)
        self.agent.db.close()
        self.agent = m.Agent(self.config, self.api)
        with self.assertRaises(m.Stop):
            self.agent.reserve(self.package)
        with self.assertRaisesRegex(m.Stop, '未知'):
            self.agent.sync('test-batch', True)
        self.assertEqual(self.api.puts, [])

    def test_live_dedup_changed_between_check_reserve(self):
        self.agent.check(self.package)
        self.api.records['other'] = dict(id='other', company='Example Company', role='Application Engineer', stage='已投递', url=self.job['url'])
        with self.assertRaises(m.Stop):
            self.agent.reserve(self.package)

    def test_legacy_smtp_lock_blocks_without_mutation(self):
        path = self.root/'old.sqlite3'
        db = sqlite3.connect(path)
        db.execute('CREATE TABLE jobs(job_key TEXT)')
        db.execute('INSERT INTO jobs VALUES (?)', (m.key(self.job)+'|examplecity',))
        db.commit()
        db.close()
        before = path.read_bytes()
        self.config['legacy_lock_databases'] = [str(path)]
        with self.assertRaisesRegex(m.Stop, '旧SMTP'):
            self.agent.check(self.package)
        self.assertEqual(before, path.read_bytes())

    def test_dry_run_and_snapshot_then_preview_complete(self):
        self.confirmed()
        original = Path(self.job['resume']['path']).read_bytes()
        Path(self.job['resume']['path']).write_bytes(b'%PDF-new-source-version')
        self.agent.sync('test-batch')
        self.assertEqual(self.api.puts, [])
        self.agent.sync('test-batch', True)
        self.assertEqual(self.api.pdfs['test-id'], original)
        self.assertEqual(self.api.records['test-id']['stage'], '已投递')
        self.assertEqual(self.agent.status('test-batch')[0]['sync'], 'bytes_verified')
        self.agent.preview('test-batch', m.key(self.job), dict(application_id='test-id', resume_sha256=m.sha(original), passed=True, checked_at=m.stamp(), artifact=self.file('cloud-preview.png', b'synthetic cloud preview fixture')))
        self.assertEqual(self.agent.status('test-batch')[0]['sync'], 'complete')

    def test_sync_retry_after_attachment_download_failure(self):
        self.confirmed()
        self.api.fail_download = True
        with self.assertRaises(m.Stop):
            self.agent.sync('test-batch', True)
        self.api.fail_download = False
        self.agent.sync('test-batch', True)
        self.assertEqual(len(self.api.records), 1)
        self.assertEqual(self.api.puts.count('/api/applications/test-id/resume'), 1)
        self.assertEqual(self.agent.status('test-batch')[0]['outcome'], 'confirmed')

    def test_no_overwrite_foreign_resume(self):
        self.confirmed()
        self.api.records['test-id'] = dict(id='test-id', company=self.job['company'], role=self.job['role'], stage='已投递', resume_name='different.pdf', resume_version=2, url=self.job['url'])
        self.api.pdfs['test-id'] = b'%PDF-other'
        with self.assertRaisesRegex(m.Stop, '禁止覆盖'):
            self.agent.sync('test-batch', True)
        self.assertEqual(self.api.pdfs['test-id'], b'%PDF-other')

    def test_preserve_interview_stage_and_existing_notes(self):
        self.confirmed()
        self.agent.sync('test-batch', True)
        self.api.records['test-id'].update(stage='面试', notes=self.api.records['test-id']['notes']+'\nuser update')
        self.agent.sync('test-batch', True)
        self.assertEqual(self.api.records['test-id']['stage'], '面试')
        self.assertTrue(self.api.records['test-id']['notes'].endswith('user update'))

    def test_wrong_receipt_cannot_confirm(self):
        self.agent.reserve(self.package)
        receipt = self.receipt()
        receipt['job_id'] = 'another-job'
        with self.assertRaises(m.Stop):
            self.agent.confirm('test-batch', m.key(self.job), 'confirmed', receipt)
        self.assertEqual(self.agent.status('test-batch')[0]['outcome'], 'unknown')

    def test_same_pdf_for_two_jobs_blocked(self):
        other = copy.deepcopy(self.job)
        other.update(job_id='job-2', application_id='test-2')
        self.package['jobs'].append(other)
        self.package['authorization']['max_submissions'] = 2
        with self.assertRaisesRegex(m.Stop, '同一PDF'):
            self.agent.check(self.package)

    def test_missing_user_confirmation_blocked(self):
        self.job['requires_user_confirmation'] = True
        with self.assertRaisesRegex(m.Stop, '指定确认'):
            self.agent.check(self.package)

    def test_dedup_job_id_is_not_substring(self):
        self.job['job_id'] = '123'
        row = dict(id='other', company=self.job['company'], role='different title', url='https://example.test/jobs/1234')
        self.assertEqual(m.matches(self.job, [row]), [])

    def test_preview_cannot_complete_before_byte_verification(self):
        self.confirmed()
        with self.assertRaisesRegex(m.Stop, '字节核验'):
            self.agent.preview('test-batch', m.key(self.job), {})

    def test_resync_keeps_completed_preview(self):
        self.test_dry_run_and_snapshot_then_preview_complete()
        result = self.agent.sync('test-batch', True)[0]
        self.assertEqual(result['state'], 'complete')
        self.assertEqual(result['preview'], 'complete')
        self.assertEqual(result['next_action'], self.agent.status('test-batch')[0]['next_action'])
        self.assertEqual(self.agent.status('test-batch')[0]['sync'], 'complete')

    def test_status_distinguishes_unknown_sync_and_preview(self):
        self.agent.reserve(self.package)
        self.assertIn('不重新投递', self.agent.status('test-batch')[0]['next_action'])
        self.agent.confirm('test-batch', m.key(self.job), 'confirmed', self.receipt())
        self.assertIn('补同步', self.agent.status('test-batch')[0]['next_action'])
        result = self.agent.sync('test-batch', True)[0]
        self.assertEqual(result['preview'], 'pending')
        self.assertEqual(result['state'], 'bytes_verified')
        self.assertIn('preview', result['next_action'])

    def test_expired_permit_not_accepted_as_compliant(self):
        self.agent.reserve(self.package)
        self.agent.db.execute('UPDATE executions SET reserved_at=?', ('2000-01-01T00:00:00+00:00',))
        self.agent.db.commit()
        with self.assertRaisesRegex(m.Stop, '有效期'):
            self.agent.confirm('test-batch', m.key(self.job), 'confirmed', self.receipt())

    def test_authorized_limit_checked_before_any_write(self):
        self.package['authorization']['max_submissions'] = 0
        with self.assertRaisesRegex(m.Stop, '授权数量'):
            self.agent.reserve(self.package)
        self.assertEqual(self.api.puts, [])

    def test_cannot_reuse_same_pdf_across_separate_batches(self):
        self.package['authorization']['max_submissions'] = 2
        self.agent.reserve(self.package)
        package = copy.deepcopy(self.package)
        package['batch_id'] = 'another-batch'
        package['jobs'][0].update(job_id='another-job', application_id='another-id', role='Another role')
        with self.assertRaisesRegex(m.Stop, '跨批'):
            self.agent.reserve(package)

    def test_cumulative_authorization_limit(self):
        self.agent.reserve(self.package)
        package = copy.deepcopy(self.package)
        package['batch_id'] = 'another-batch'
        package['jobs'][0].update(job_id='another-job', application_id='another-id')
        with self.assertRaisesRegex(m.Stop, '累计'):
            self.agent.reserve(package)

    def test_two_jobs_cannot_share_cloud_record_id(self):
        other = copy.deepcopy(self.job)
        other['job_id'] = 'another-job'
        self.package['jobs'].append(other)
        self.package['authorization']['max_submissions'] = 2
        with self.assertRaisesRegex(m.Stop, '记录ID'):
            self.agent.check(self.package)


class HTTPTests(unittest.TestCase):
    def test_real_http_adapter_with_synthetic_token_and_server(self):
        # Only this test overrides an already-validated client's URL to loopback.
        # Production constructor still rejects HTTP; no real credentials are used.
        owner = self
        storage = FakeOfferPath()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                owner.assertEqual(self.headers.get('Authorization'), 'Bearer synthetic-test-token')
                result = m.encoded(storage.rows()) if self.path == '/api/applications' else storage.request(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(result)

            def do_PUT(self):
                data = self.rfile.read(int(self.headers['Content-Length']))
                headers = {k.lower(): v for k, v in self.headers.items()}
                storage.request(self.path, 'PUT', data, headers)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{}')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = m.OfferPath({'offerpath': {'base_url': 'https://example.test'}})
            client.base = 'http://127.0.0.1:' + str(server.server_port)
            client.token = 'synthetic-test-token'
            fixture = AgentTests()
            fixture.setUp()
            try:
                fixture.agent.api = client
                fixture.confirmed()
                fixture.agent.sync('test-batch', True)
                self.assertEqual(storage.records['test-id']['stage'], '已投递')
                self.assertEqual(storage.pdfs['test-id'], Path(fixture.job['resume']['path']).read_bytes())
                self.assertEqual(fixture.agent.status('test-batch')[0]['sync'], 'bytes_verified')
            finally:
                fixture.tearDown()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_non_https_or_embedded_credentials_rejected(self):
        for url in ('http://example.test', 'https://user:pass@example.test', 'https://example.test/?token=x'):
            with self.assertRaises(m.Stop):
                m.OfferPath({'offerpath': {'base_url': url}})


if __name__ == '__main__':
    unittest.main()
