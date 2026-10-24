"""Offline synthetic workflow demo. Never contacts OfferPath or a recruiter."""
import argparse
import copy
import html
import json
from pathlib import Path

import agent
from setup import outside_repository


class MemoryOfferPath:
    """In-memory API substitute; no HTTP, credentials, or real account."""
    def __init__(self):
        self.records, self.pdfs = {}, {}

    def rows(self):
        return copy.deepcopy(list(self.records.values()))

    def request(self, path, method='GET', data=None, headers=None):
        record_id = path.split('/')[3]
        if path.endswith('/resume'):
            if method == 'PUT':
                current = self.records[record_id]
                agent.require(headers['if-match'] == str(current['resume_version']), 'Demo version conflict')
                self.pdfs[record_id] = data
                current.update(resume_name=agent.urllib.parse.unquote(headers['x-resume-name']), resume_version=current['resume_version'] + 1)
                return b'{}'
            return self.pdfs[record_id]
        agent.require(method == 'PUT', 'Unsupported demo request')
        record = json.loads(data)
        record.setdefault('resume_version', 0)
        self.records[record_id] = record
        return b'{}'


def pdf(text):
    """Small, valid one-page synthetic PDF using built-in Helvetica."""
    safe = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    stream = ('BT /F1 14 Tf 50 750 Td (' + safe + ') Tj ET').encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    result, offsets = b'%PDF-1.4\n', [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result += str(index).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    start = len(result)
    result += b'xref\n0 6\n0000000000 65535 f \n'
    result += b''.join(('%010d 00000 n \n' % offset).encode() for offset in offsets[1:])
    return result + ('trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % start).encode()


def run(destination):
    root = outside_repository(destination)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)

    def artifact(name, data):
        path = root / name
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        return {'path': str(path), 'sha256': agent.sha(path.read_bytes())}

    def save(name, value):
        return artifact(name, json.dumps(value, ensure_ascii=False, indent=2))

    jd = 'SYNTHETIC ROLE: Example Studio, Integration Engineer. Build Python APIs and reliable data pipelines. Example City. Salary not disclosed. Fictional full job description for offline demonstration only.'
    before = 'SYNTHETIC candidate: Software engineer with project experience.'
    after = 'SYNTHETIC candidate: Built Python APIs and validated pipeline data in a fictional project.'
    policy = artifact('policy.md', 'SYNTHETIC DEMO ONLY. No real submission authorized.')
    base = artifact('base.pdf', pdf(before))
    resume = artifact('tailored.pdf', pdf(after))
    job = dict(company='Example Studio (fictional)', role='Integration Engineer', job_id='demo-job-1',
               location='Example City', url='https://example.test/jobs/demo-job-1', channel='offline-simulator',
               application_id='demo-record-1', verified_at=agent.stamp(),
               screening={k: 'SYNTHETIC example; no real eligibility assessment' for k in ('employer', 'location', 'duties', 'qualifications', 'salary', 'posting_date', 'employment', 'language')},
               jd=artifact('jd.txt', jd), base_resume=base, resume=resume, source=artifact('resume-source.txt', after),
               tailoring=dict(substantive_reviewed=True, changes=['Synthetic example emphasizes API and pipeline experience'],
                              mapping=[dict(requirement='Python APIs and pipelines', evidence=after, fact_source='fictional facts in this demo')],
                              diff=artifact('tailoring.md', '# SYNTHETIC tailoring example\n\nBefore: ' + before + '\n\nAfter: ' + after)),
               visual=dict(passed=True, checked_at=agent.stamp(), pages=1, resume_sha256=resume['sha256'],
                           previews=[artifact('synthetic-review.txt', 'SIMULATED assertion for offline gate demonstration. Not a real rendered visual review.')]),
               form_reviewed=True, requires_user_confirmation=False, selected_attachment_sha256=resume['sha256'])
    job['screening']['passed'] = True
    package = dict(version=1, batch_id='synthetic-demo', policy_sha256=policy['sha256'],
                   authorization=dict(action='apply', user_instruction_ref='SYNTHETIC-NO-REAL-SENDING', max_submissions=1), jobs=[job])
    save('package.json', package)
    api = MemoryOfferPath()
    executor = agent.Agent(dict(policy_path=policy['path'], state_db=str(root / 'demo.sqlite3'), resume_pages=1), api)
    try:
        executor.check(package)
        executor.reserve(package)
        unknown = executor.status('synthetic-demo')
        receipt = dict(application_id=job['application_id'], job_id=job['job_id'], resume_sha256=resume['sha256'],
                       kind='platform_success', summary='SIMULATED receipt; no real application', observed_at=agent.stamp(),
                       submitted_at=agent.stamp(), artifact=artifact('receipt.txt', 'SIMULATED SUCCESS. No recruiter contacted.'))
        save('receipt.json', receipt)
        executor.confirm('synthetic-demo', agent.key(job), 'confirmed', receipt)
        dry_run = executor.sync('synthetic-demo')
        synced = executor.sync('synthetic-demo', True)
        evidence = dict(application_id=job['application_id'], resume_sha256=resume['sha256'], passed=True,
                        checked_at=agent.stamp(), artifact=artifact('synthetic-cloud-review.txt', 'SIMULATED preview of in-memory attachment; no real cloud preview.'))
        executor.preview('synthetic-demo', agent.key(job), evidence)
        repeated = executor.sync('synthetic-demo', True)
        final = executor.status('synthetic-demo')
        report = dict(synthetic=True, network_requests=0, real_applications=0, real_cloud_writes=0,
                      visual_reviews='simulated assertions only', unknown=unknown, dry_run=dry_run,
                      first_sync=synced, repeated_sync=repeated, final=final, simulated_records=api.rows())
        save('report.json', report)
        page = '<!doctype html><html lang="en"><meta charset="utf-8"><title>OfferPath synthetic demo</title><style>body{font:17px system-ui;max-width:900px;margin:40px auto;padding:24px;background:#fff8ed;color:#16324c}pre{white-space:pre-wrap;background:#e9f2fa;padding:20px;border-radius:16px}</style><h1>🤖 OfferPath · Offline synthetic demo</h1><p>No real applications, accounts, credentials, network calls, or cloud writes. Visual-review assertions are simulated. This is not a real OfferPath screenshot.</p>'
        page += '<h2>1. Fictional job description</h2><p>' + html.escape(jd) + '</p><h2>2. Tailoring example</h2><p>Before: ' + html.escape(before) + '</p><p>After: ' + html.escape(after) + '</p><h2>3. Workflow result and simulated record</h2><pre>' + html.escape(json.dumps(report, ensure_ascii=False, indent=2)) + '</pre><p><a href="https://offerpath.xingo.fun">Explore the real OfferPath website</a> (optional external link)</p></html>'
        artifact('index.html', page)
        return {'synthetic': True, 'report': str(root / 'index.html'), 'final': final,
                'network_requests': 0, 'real_applications': 0, 'real_cloud_writes': 0}
    finally:
        executor.db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='New directory outside repository')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError, agent.Stop) as exc:
        parser.exit(1, str(exc) + '\n')
