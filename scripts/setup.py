"""Create a private workspace without credentials or network access."""
import argparse
import json
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def outside_repository(path):
    path = Path(path).expanduser().resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('个人工作区必须位于项目仓库外 / Choose a directory outside this repository')
    return path


def initialize(destination):
    root = outside_repository(destination)
    # Exclusive creation prevents overwriting existing configurations, including retries.
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name in ('runtime', 'batches'):
        (root / name).mkdir(mode=0o700)
    config = json.loads((ROOT / 'examples/private-config.example.json').read_text())
    for key, name in [('policy_path', 'policy.md'), ('profile_path', 'profile.md'),
                      ('workbench_path', 'workbench.md'), ('facts_path', 'facts.md'),
                      ('batch_root', 'batches'), ('state_db', 'runtime/executions.sqlite3')]:
        config[key] = str(root / name)
    files = {
        'agent.local.json': json.dumps(config, ensure_ascii=False, indent=2) + '\n',
        'profile.md': (ROOT / 'examples/profile.example.md').read_text(),
        'policy.md': (ROOT / 'examples/policy.example.md').read_text(),
        'facts.md': '# Verified facts / 已确认事实\n\nAdd only experience you can substantiate. No invented claims.\n',
        'workbench.md': '# Job search workbench / 求职工作台\n\nNo applications yet. OfferPath is the live status source.\n',
        'AGENTS.md': '# Private job workspace\n\nUse $offerpath-job-agent with private configuration: ' + str(root / 'agent.local.json') + '\nRead profile.md, facts.md and policy.md before work. Configuration is not authorization to apply.\n',
        '.gitignore': '*\n!.gitignore\n',
    }
    for name, content in files.items():
        target = root / name
        with target.open('x') as stream:
            stream.write(content)
        target.chmod(0o600)
    return {'workspace': str(root), 'config': str(root / 'agent.local.json'),
            'ready_for_live_use': False, 'network_requests': 0,
            'next_steps': ['填写个人偏好与真实事实 / Complete profile and verified facts',
                           '在JSON中引用本人既有钥匙串条目，不填写令牌 / Reference your own existing Keychain entry',
                           '准备好后运行agent.py doctor；这不是投递授权 / Run doctor when ready; no sending authorization is granted']}


def check_local(config_path):
    path = Path(config_path).expanduser().resolve()
    outside_repository(path)
    config = json.loads(path.read_text())
    if not isinstance(config, dict):
        raise ValueError('配置必须是JSON对象 / Configuration must be a JSON object')
    problems = []
    for key in ('policy_path', 'profile_path', 'workbench_path', 'facts_path', 'batch_root', 'state_db'):
        value = config.get(key)
        if not isinstance(value, str) or not Path(value).is_absolute():
            problems.append(key + ': 需要绝对路径 / absolute path required')
            continue
        try:
            target = outside_repository(value)
        except ValueError:
            problems.append(key + ': 路径必须在仓库外 / must be outside repository')
            continue
        if key != 'state_db' and not (target.is_dir() if key == 'batch_root' else target.is_file()):
            problems.append(key + ': 文件或目录不存在 / missing file or directory')
    offerpath = config.get('offerpath')
    if not isinstance(offerpath, dict):
        offerpath = {}
    keychain = offerpath.get('keychain')
    if not isinstance(keychain, dict):
        keychain = {}
    if any(not keychain.get(k) or str(keychain[k]).startswith('your-existing-') for k in ('service', 'account')):
        problems.append('钥匙串引用仍为样例 / Keychain references need configuration')
    try:
        url = urllib.parse.urlsplit(offerpath.get('base_url', '').rstrip('/'))
        valid_url = url.scheme == 'https' and url.hostname and not any((url.username, url.password, url.path, url.query, url.fragment))
    except (ValueError, AttributeError, TypeError):
        valid_url = False
    if not valid_url:
        problems.append('offerpath.base_url: 需要不含凭据或路径的HTTPS源站 / HTTPS origin required')
    if type(config.get('resume_pages')) is not int or config['resume_pages'] < 1:
        problems.append('resume_pages: 需要正整数 / positive integer required')
    return {'local_checks_passed': not problems, 'problems': problems, 'network_requests': 0,
            'meaning': '仅本地配置检查；未核验凭据、资料内容或线上连接 / Local checks only; no credentials or live connection verified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    init = sub.add_parser('init')
    init.add_argument('--workspace', help='New directory outside repository; prompts if omitted')
    check = sub.add_parser('check')
    check.add_argument('--config', required=True)
    args = parser.parse_args()
    try:
        if args.action == 'init':
            destination = args.workspace or input('新私有目录 / New private workspace path: ').strip()
            if not destination:
                raise ValueError('未提供目录 / No directory provided')
            result = initialize(destination)
        else:
            result = check_local(args.config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('local_checks_passed') is False else 0
    except (OSError, ValueError, TypeError) as exc:
        print('配置未完成 / Setup incomplete: ' + str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
