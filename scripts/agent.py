"""Local application gate + receipt-based OfferPath sync. No job/email sender."""
import argparse
import copy
import datetime as dt
import hashlib
import json
import re
import sqlite3
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path


class Stop(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise Stop(message)


def now():
    return dt.datetime.now(dt.timezone.utc)


def stamp():
    return now().isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()


def norm(s):
    return re.sub(r'\s+', '', s).casefold()


def fresh(value, seconds=86400):
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(parsed.tzinfo is not None, '时间必须含时区')
        require(0 <= (now() - parsed).total_seconds() <= seconds, '核验过期或时间在未来')
    except (ValueError, TypeError, AttributeError):
        raise Stop('无效核验时间') from None


def artifact(item):
    path = Path(item['path'])
    require(path.is_absolute() and path.is_file(), '证据文件不存在或不是绝对路径')
    data = path.read_bytes()
    require(data and sha(data) == item['sha256'], '材料或证据哈希不一致')
    return data


def key(job):
    return norm(job['company']) + '|' + norm(job['job_id'])


def legacy_check(config, job):
    """Read existing SMTP locks without creating, mutating or resetting that DB."""
    for name in config.get('legacy_lock_databases', []):
        path = Path(name)
        require(path.is_file(), '旧发送状态库不可读取')
        try:
            db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
            try:
                keys = [r[0] for r in db.execute('SELECT job_key FROM jobs')]
            finally:
                db.close()
        except sqlite3.Error:
            raise Stop('旧发送状态库结构不可核验') from None
        prefix = norm(job['company']) + '|'
        candidates = {norm(job['job_id']), norm(job['role'])}
        require(not any(k.startswith(prefix) and k.split('|')[1] in candidates for k in keys),
                '旧SMTP通道已有岗位锁，禁止再次外发')


def validate(package, config):
    require(package.get('version') == 1, '不支持的申请包版本')
    require(package.get('authorization', {}).get('action') == 'apply', '缺少本批投递授权记录')
    require(package['authorization'].get('user_instruction_ref'), '缺少用户授权来源')
    require(package.get('batch_id') and package.get('jobs'), '缺少批次或岗位')
    require(0 < len(package['jobs']) <= package['authorization'].get('max_submissions', 0), '超过授权数量')
    artifact({'path': config['policy_path'], 'sha256': package['policy_sha256']})
    materials, identities, resume_hashes, record_ids = [], set(), set(), set()
    for job in package['jobs']:
        for field in ('company', 'role', 'job_id', 'location', 'url', 'application_id', 'channel'):
            require(isinstance(job.get(field), str) and job[field].strip(), '岗位身份字段缺失: ' + field)
        require(re.fullmatch(r'[A-Za-z0-9_-]+', job['application_id']), '非法OfferPath记录ID')
        require(job['url'].startswith('https://'), '缺少安全的申请入口')
        require(key(job) not in identities, '申请包内重复岗位')
        require(job['application_id'] not in record_ids, '不同岗位不能绑定同一OfferPath记录ID')
        record_ids.add(job['application_id'])
        identities.add(key(job))
        fresh(job['verified_at'])
        screening = job.get('screening', {})
        for field in ('employer', 'location', 'duties', 'qualifications', 'salary', 'posting_date', 'employment', 'language'):
            require(screening.get(field), '缺少筛选依据: ' + field)
        require(screening.get('passed') is True, '岗位未通过个人配置筛选')
        artifact(job['jd'])
        data = artifact(job['resume'])
        require(data.startswith(b'%PDF-') and len(data) <= 10_000_000, 'PDF格式或大小不合格')
        base = artifact(job['base_resume'])
        require(sha(data) != sha(base), '禁止直接投递通用母版或改名副本')
        require(sha(data) not in resume_hashes, '不同岗位不能复用同一PDF')
        resume_hashes.add(sha(data))
        artifact(job['source'])
        tailoring = job.get('tailoring', {})
        require(tailoring.get('substantive_reviewed') is True, '未审阅实质定制')
        require(tailoring.get('changes'), '缺少具体定制改动')
        for mapping in tailoring.get('mapping', []):
            require(mapping.get('requirement') and mapping.get('evidence') and mapping.get('fact_source'), 'JD事实映射不完整')
        require(tailoring.get('mapping'), '缺少JD与经历映射')
        artifact(tailoring['diff'])
        visual = job.get('visual', {})
        require(visual.get('passed') is True and visual.get('resume_sha256') == sha(data), '视觉验收未绑定最终PDF')
        fresh(visual['checked_at'])
        require(visual.get('pages') == config.get('resume_pages', 1), '简历页数不符合个人配置')
        require(visual.get('previews'), '缺少渲染预览')
        for preview in visual['previews']:
            artifact(preview)
        require(job.get('form_reviewed') is True and job.get('selected_attachment_sha256') == sha(data), '表单/拟上传附件未核对')
        require(job.get('requires_user_confirmation') is False or job.get('user_confirmation_ref'), '缺少本人指定确认')
        legacy_check(config, job)
        materials.append(data)
    return materials


def matches(job, rows):
    result = []
    for row in rows:
        same_company = norm(row.get('company', '')) == norm(job['company'])
        # IDs must match whole URL tokens, not arbitrary numeric substrings.
        tokens = re.split(r'[^\w-]+', urllib.parse.unquote(row.get('url') or ''))
        if row['id'] == job['application_id'] or (same_company and
                (norm(row.get('role', '')) == norm(job['role']) or job['job_id'] in tokens)):
            result.append(row)
    return result


class OfferPath:
    def __init__(self, config):
        self.config = config
        self.token = None
        self.base = config['offerpath']['base_url'].rstrip('/')
        url = urllib.parse.urlsplit(self.base)
        require(url.scheme == 'https' and url.hostname and not url.username and not url.password
                and not url.query and not url.fragment and not url.path, 'OfferPath必须使用HTTPS源站地址')

    def request(self, path, method='GET', data=None, headers=None):
        require(re.fullmatch(r'/api/applications(?:/[A-Za-z0-9_-]+(?:/resume)?)?', path), '接口范围不允许')
        require(method in ('GET', 'PUT'), '仅允许记录与附件读写')
        if self.token is None:
            secret = self.config['offerpath']['keychain']
            p = subprocess.run(['security', 'find-generic-password', '-s', secret['service'], '-a', secret['account'], '-w'], capture_output=True, text=True)
            require(p.returncode == 0 and p.stdout.strip(), '既有钥匙串凭据不可用；由本人处理，禁止查找其他秘密')
            self.token = p.stdout.strip()
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            'Authorization': 'Bearer ' + self.token, 'Accept': 'application/json',
            'User-Agent': 'OfferPath-Job-Agent/1.0', **(headers or {})})
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
                return response.read()
        except Exception:
            raise Stop('OfferPath请求失败；保留检查点，仅补同步，不重新投递') from None

    def rows(self):
        rows = json.loads(self.request('/api/applications'))
        require(isinstance(rows, list), '台账返回格式异常')
        return rows


class Agent:
    def __init__(self, config, api):
        self.config, self.api = config, api
        path = Path(config['state_db'])
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        path.chmod(0o600)
        self.db.execute('CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, fingerprint TEXT, package TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS executions (job_key TEXT PRIMARY KEY, batch_id TEXT, job TEXT, pdf BLOB, state TEXT, receipt TEXT, sync_state TEXT, reserved_at TEXT, preview TEXT)')
        self.db.commit()

    def check(self, package):
        data = validate(package, self.config)
        prior = self.db.execute('SELECT package FROM batches').fetchall()
        authorized = package['authorization']
        used = sum(len(p['jobs']) for p in (json.loads(r[0]) for r in prior)
                   if p['authorization']['user_instruction_ref'] == authorized['user_instruction_ref'])
        require(used + len(package['jobs']) <= authorized['max_submissions'], '同一授权下累计保留岗位超过上限')
        rows = self.api.rows()
        for job, pdf in zip(package['jobs'], data):
            require(not self.db.execute('SELECT 1 FROM executions WHERE job_key=?', (key(job),)).fetchone(), '已有执行锁，只能查证或补同步')
            require(not any(sha(r[0]) == sha(pdf) for r in self.db.execute('SELECT pdf FROM executions WHERE job_key<>?', (key(job),))), '另一岗位已使用同一PDF，禁止跨批复用通用稿')
            found = matches(job, rows)
            require(len(found) <= 1, '台账匹配歧义，停止')
            if found:
                require(found[0]['id'] == job['application_id'] and found[0]['stage'] == '想投', '已有投递/关闭/面试或其他记录，禁止外发')
                require(norm(found[0]['company']) == norm(job['company']) and norm(found[0]['role']) == norm(job['role']), '台账身份不符')
                if found[0].get('resume_name'):
                    require(self.api.request('/api/applications/' + job['application_id'] + '/resume') == data[package['jobs'].index(job)], '已有云端附件不同，停止')
        return sha(encoded(package)), data

    def reserve(self, package):
        fingerprint, materials = self.check(package)
        try:
            self.db.execute('BEGIN IMMEDIATE')
            authorized = package['authorization']
            used = sum(len(p['jobs']) for p in (json.loads(r[0]) for r in self.db.execute('SELECT package FROM batches'))
                       if p['authorization']['user_instruction_ref'] == authorized['user_instruction_ref'])
            require(used + len(package['jobs']) <= authorized['max_submissions'], '同一授权累计数量超限')
            self.db.execute('INSERT INTO batches VALUES (?,?,?)', (package['batch_id'], fingerprint, encoded(package).decode()))
            for job, pdf in zip(package['jobs'], materials):
                self.db.execute('INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?)',
                    (key(job), package['batch_id'], encoded(job).decode(), pdf, 'unknown', None, 'pending', stamp(), None))
            self.db.commit()
        except (sqlite3.Error, Stop):
            self.db.rollback()
            raise Stop('执行保留失败或已有锁；未取得许可，禁止外发') from None
        return {'batch_id': package['batch_id'], 'fingerprint': fingerprint, 'permit_seconds': 600,
                'jobs': [{'job_key': key(j), 'application_id': j['application_id'], 'resume_sha256': j['resume']['sha256']} for j in package['jobs']],
                'meaning': '材料检查与本地保留完成；不是已投，也不是用户授权'}

    def confirm(self, batch_id, job_key, outcome, evidence):
        row = self.db.execute('SELECT job,reserved_at,state,receipt FROM executions WHERE job_key=? AND batch_id=?', (job_key, batch_id)).fetchone()
        require(row, '不存在保留记录')
        artifact(evidence['artifact'])
        job = json.loads(row[0])
        require(evidence.get('application_id') == job['application_id'] and evidence.get('job_id') == job['job_id'], '回执岗位身份不一致')
        require(evidence.get('resume_sha256') == job['resume']['sha256'], '回执附件版本不一致')
        require(evidence.get('summary') and evidence.get('observed_at'), '缺少回执说明或时间')
        fresh(evidence['observed_at'])
        if outcome == 'confirmed':
            require(evidence.get('kind') in ('platform_success', 'candidate_center', 'smtp_accepted'), '没有成功投递证据')
            sent = dt.datetime.fromisoformat(evidence['submitted_at'].replace('Z', '+00:00'))
            reserved = dt.datetime.fromisoformat(row[1])
            require(0 <= (sent - reserved).total_seconds() <= 600, '提交时间不在许可有效期，需人工审计，不自动认定流程合格')
            require(sent <= now(), '提交时间在未来')
        require(row[2] != 'confirmed' or (outcome == 'confirmed' and json.loads(row[3]) == evidence), '不能覆盖已确认回执')
        self.db.execute('UPDATE executions SET state=?,receipt=? WHERE job_key=?', (outcome, encoded(evidence).decode(), job_key))
        self.db.commit()

    def sync(self, batch_id, write=False):
        executions = self.db.execute('SELECT job_key,job,pdf,state,receipt FROM executions WHERE batch_id=?', (batch_id,)).fetchall()
        require(executions, '批次不存在')
        results = []
        for job_key, raw, pdf, state, receipt_raw in executions:
            require(state == 'confirmed', '存在结果未知的申请，禁止标已投')
            job, receipt = json.loads(raw), json.loads(receipt_raw)
            require(sha(pdf) == job['resume']['sha256'], '实际投递快照损坏')
            found = matches(job, self.api.rows())
            require(len(found) <= 1, '台账匹配歧义')
            require(not found or found[0]['id'] == job['application_id'], '同岗已有不同记录，需人工核查，禁止另建')
            if found:
                require(norm(found[0]['company']) == norm(job['company']) and norm(found[0]['role']) == norm(job['role']), '记录ID对应其他岗位')
            if not write:
                results.append({'application_id': job['application_id'], 'action': 'update' if found else 'create', 'dry_run': True})
                continue
            path = '/api/applications/' + job['application_id']
            note = ('OfferPath Job Agent batch=' + batch_id + '; job_id=' + job['job_id'] +
                    '\n回执：' + receipt['summary'] + '\n回执证据：' + receipt['artifact']['path'] +
                    '\n本地实际投递件：' + job['resume']['path'] + '\n实际PDF字节数：' + str(len(pdf)) +
                    '\n实际PDF SHA256：' + sha(pdf) + '\n完整JD：' + job['jd']['path'] +
                    '\n定制说明：' + job['tailoring']['diff']['path'] + '\n视觉验收：' + job['visual']['checked_at'] +
                    '\n流程：已绑定逐岗定制及验收记录；云端预览完成情况见本地执行状态。' +
                    '\n申请字段留档：' + json.dumps(job.get('application_answers', {}), ensure_ascii=False) +
                    '\n筛选：' + json.dumps(job['screening'], ensure_ascii=False))
            marker = 'OfferPath Job Agent batch=' + batch_id + '; job_id=' + job['job_id']
            if not found:
                record = dict(id=job['application_id'], company=job['company'], role=job['role'], location=job['location'], company_type='待确认', stage='想投', stage_at=stamp(), source=job['channel'], url=job['url'], notes=note, next_action=job.get('next_action') or '等待反馈；按实际结果更新', activities_json='[]', favorite=False, updated_at=stamp())
                self.api.request(path, 'PUT', encoded(record), {'content-type': 'application/json'})
            current = next(r for r in self.api.rows() if r['id'] == job['application_id'])
            if current.get('resume_name'):
                require(current['resume_name'] == Path(job['resume']['path']).name and self.api.request(path + '/resume') == pdf, '已有附件与投递快照不同，禁止覆盖')
            else:
                self.api.request(path + '/resume', 'PUT', pdf, {'content-type': 'application/pdf', 'x-resume-name': urllib.parse.quote(Path(job['resume']['path']).name), 'if-match': str(current['resume_version'])})
            require(self.api.request(path + '/resume') == pdf, '云端附件字节回读不一致')
            # Re-read before update; preserve interviews/closed states and user edits.
            current = next(r for r in self.api.rows() if r['id'] == job['application_id'])
            updated = copy.deepcopy(current)
            if current['stage'] == '想投':
                updated.update(stage='已投递', stage_at=receipt['submitted_at'])
            updated['applied_at'] = current.get('applied_at') or dt.datetime.fromisoformat(receipt['submitted_at'].replace('Z', '+00:00')).astimezone(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
            if marker not in (current.get('notes') or ''):
                updated['notes'] = (current.get('notes') or '') + '\n' + note
            if updated != current:
                updated['updated_at'] = stamp()
                self.api.request(path, 'PUT', encoded(updated), {'content-type': 'application/json'})
            actual = next(r for r in self.api.rows() if r['id'] == job['application_id'])
            require(actual.get('applied_at') and marker in (actual.get('notes') or '') and actual.get('resume_name') == Path(job['resume']['path']).name and self.api.request(path + '/resume') == pdf, '最终回读失败')
            self.db.execute("UPDATE executions SET sync_state=CASE WHEN sync_state='complete' THEN 'complete' ELSE 'bytes_verified' END WHERE job_key=?", (job_key,))
            self.db.commit()
            results.append({'application_id': job['application_id'], 'state': 'bytes_verified', 'sha256': sha(pdf), 'bytes': len(pdf), 'stage': actual['stage'], 'preview': 'pending'})
        return results

    def preview(self, batch_id, job_key, evidence):
        row = self.db.execute('SELECT job,sync_state FROM executions WHERE batch_id=? AND job_key=?', (batch_id, job_key)).fetchone()
        require(row and row[1] in ('bytes_verified', 'complete'), '尚未完成附件字节核验')
        job = json.loads(row[0])
        require(evidence.get('application_id') == job['application_id'] and evidence.get('resume_sha256') == job['resume']['sha256'] and evidence.get('passed') is True, '预览证据未绑定岗位与附件')
        fresh(evidence['checked_at'])
        artifact(evidence['artifact'])
        require(self.api.request('/api/applications/' + job['application_id'] + '/resume') == self.db.execute('SELECT pdf FROM executions WHERE job_key=?', (job_key,)).fetchone()[0], '预览确认前附件已变化')
        self.db.execute('UPDATE executions SET sync_state=?,preview=? WHERE job_key=?', ('complete', encoded(evidence).decode(), job_key))
        self.db.commit()

    def status(self, batch_id):
        return [dict(job_key=r[0], outcome=r[1], sync=r[2], application_id=json.loads(r[3])['application_id']) for r in self.db.execute('SELECT job_key,state,sync_state,job FROM executions WHERE batch_id=?', (batch_id,))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('action', choices=['doctor', 'check', 'reserve', 'confirm', 'sync', 'preview', 'status'])
    parser.add_argument('--package')
    parser.add_argument('--batch')
    parser.add_argument('--job-key')
    parser.add_argument('--evidence')
    parser.add_argument('--outcome', choices=['unknown', 'confirmed'])
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    agent = Agent(config, OfferPath(config))
    if args.action == 'doctor':
        for name in ('policy_path', 'profile_path', 'workbench_path', 'facts_path'):
            require(Path(config[name]).is_file(), '私有资料入口不可用: ' + name)
        require(Path(config['batch_root']).is_dir(), '批次目录不可用')
        for name in config.get('legacy_lock_databases', []):
            require(Path(name).is_file(), '旧发送状态库不可用')
        before = sha(encoded(agent.api.rows()))
        rows = agent.api.rows()
        require(before == sha(encoded(rows)), '只读核验期间台账变化，需重新检查')
        result = {'state': 'read_only_connection_verified', 'records': len(rows), 'records_sha256': before,
                  'writes': 0, 'meaning': '私有入口与正式台账只读连通；未进行真实上传或投递测试'}
    elif args.action in ('check', 'reserve'):
        package = json.loads(Path(args.package).read_text())
        result = agent.reserve(package) if args.action == 'reserve' else {'fingerprint': agent.check(package)[0], 'state': 'checked_not_reserved'}
    elif args.action == 'confirm':
        require(args.outcome, '必须指定回执结果')
        agent.confirm(args.batch, args.job_key, args.outcome, json.loads(Path(args.evidence).read_text()))
        result = agent.status(args.batch)
    elif args.action == 'sync':
        result = agent.sync(args.batch, args.write)
    elif args.action == 'preview':
        agent.preview(args.batch, args.job_key, json.loads(Path(args.evidence).read_text()))
        result = agent.status(args.batch)
    else:
        result = agent.status(args.batch)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('停止：' + (str(exc) if isinstance(exc, Stop) else type(exc).__name__) + '；不自动重投。')
        raise SystemExit(1)
