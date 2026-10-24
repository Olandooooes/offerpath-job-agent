import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


setup = module('setup')
sys.modules['agent'] = module('agent')
sys.modules['setup'] = setup
demo = module('demo')


class OnboardingTests(unittest.TestCase):
    def test_init_private_and_non_destructive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'private'
            with patch('socket.socket', side_effect=AssertionError('No networking')):
                result = setup.initialize(root)
            self.assertFalse(result['ready_for_live_use'])
            config = json.loads((root / 'agent.local.json').read_text())
            for key in ('policy_path', 'profile_path', 'workbench_path', 'facts_path'):
                self.assertTrue(Path(config[key]).is_file())
            self.assertEqual((root / 'agent.local.json').stat().st_mode & 0o777, 0o600)
            before = (root / 'agent.local.json').read_bytes()
            with self.assertRaises(FileExistsError):
                setup.initialize(root)
            self.assertEqual((root / 'agent.local.json').read_bytes(), before)
            self.assertFalse(setup.check_local(root / 'agent.local.json')['local_checks_passed'])
            config['offerpath']['keychain'] = dict(service='synthetic-reference', account='synthetic-account')
            (root / 'agent.local.json').write_text(json.dumps(config))
            self.assertTrue(setup.check_local(root / 'agent.local.json')['local_checks_passed'])
            original_url = config['offerpath']['base_url']
            config['offerpath']['base_url'] = 'https://user:secret@example.test'
            (root / 'agent.local.json').write_text(json.dumps(config))
            self.assertFalse(setup.check_local(root / 'agent.local.json')['local_checks_passed'])
            config['offerpath']['base_url'] = original_url
            config['resume_pages'] = False
            (root / 'agent.local.json').write_text(json.dumps(config))
            self.assertFalse(setup.check_local(root / 'agent.local.json')['local_checks_passed'])
            config['resume_pages'] = 1
            (root / 'agent.local.json').write_text(json.dumps(config))
            Path(config['facts_path']).unlink()
            self.assertFalse(setup.check_local(root / 'agent.local.json')['local_checks_passed'])

    def test_repo_and_symlink_destinations_rejected(self):
        with self.assertRaises(ValueError):
            setup.initialize(setup.ROOT / 'private-test')
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / 'repo-link'
            link.symlink_to(setup.ROOT, target_is_directory=True)
            with self.assertRaises(ValueError):
                setup.initialize(link / 'private-test')

    def test_cli_init_and_check_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'private'
            init = subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), 'init', '--workspace', str(root)], capture_output=True, text=True)
            self.assertEqual(init.returncode, 0, init.stdout)
            check = subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), 'check', '--config', str(root / 'agent.local.json')], capture_output=True, text=True)
            self.assertEqual(check.returncode, 1)
            self.assertEqual(json.loads(check.stdout)['network_requests'], 0)

    def test_demo_offline_complete_and_repeat_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'demo'
            with patch('socket.socket', side_effect=AssertionError('No networking')), patch('subprocess.run', side_effect=AssertionError('No credential access')):
                result = demo.run(root)
            report = json.loads((root / 'report.json').read_text())
            self.assertEqual(result['final'][0]['sync'], 'complete')
            self.assertEqual(report['repeated_sync'][0]['preview'], 'complete')
            self.assertEqual(report['first_sync'][0]['preview'], 'pending')
            self.assertEqual(len(report['simulated_records']), 1)
            self.assertEqual(report['unknown'][0]['outcome'], 'unknown')
            self.assertEqual(report['real_applications'], 0)
            self.assertEqual(report['real_cloud_writes'], 0)
            self.assertEqual(report['network_requests'], 0)
            self.assertIn('SIMULATED', (root / 'receipt.txt').read_text())
            self.assertTrue((root / 'index.html').is_file())
            before = (root / 'report.json').read_bytes()
            with self.assertRaises(FileExistsError):
                demo.run(root)
            self.assertEqual((root / 'report.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
