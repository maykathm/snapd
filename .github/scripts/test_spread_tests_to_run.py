
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
# To ensure the unit test can be run from any point in the filesystem,
# add parent folder to path to permit relative imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import spread_tests_to_run as stt


def fake_filter(output):
    calls = []

    def run(cmd, capture_output, text, cwd):
        calls.append((cmd, cwd))
        prefix = cmd[cmd.index('-p') + 1]
        return subprocess.CompletedProcess(cmd, 0, ' '.join(prefix + ':' + o for o in output), '')

    return run, calls


class TestSpreadTestsToRun(unittest.TestCase):

    def test_pr_filters_each_system(self):
        run, calls = fake_filter(['tests/main/a', 'tests/unit/go'])
        with patch('spread_tests_to_run.subprocess.run', run):
            selectors = stt.tests_to_run('openstack', 'ubuntu-24.04-64 debian-12-64', ['tests/...'], 'main',
                                         ['tests/main/a/task.yaml', 'snap/foo_test.go'], pr=True, repo='/repo')
        self.assertEqual(selectors, [
            'openstack:ubuntu-24.04-64:tests/main/a', 'openstack:ubuntu-24.04-64:tests/unit/go',
            'openstack:debian-12-64:tests/main/a', 'openstack:debian-12-64:tests/unit/go',
        ])
        self.assertEqual(calls[0], ([
            '/repo/tests/lib/external/snapd-testing-tools/utils/spread-filter',
            '-r', '/repo/tests/lib/spread/rules/main.yaml', '-p', 'openstack:ubuntu-24.04-64',
            '-c', 'tests/main/a/task.yaml', '-c', 'snap/foo_test.go', '-t', 'tests/...',
        ], '/repo'))

    def test_all_tasks_when_not_filtered(self):
        run, calls = fake_filter([])
        cases = {
            'not a pull request': dict(pr=False),
            'run nested': dict(pr=True, run_nested=True),
            'no rules': dict(pr=True, rules=''),
            'no changes': dict(pr=True, changes=[]),
        }
        for name, kwargs in cases.items():
            with self.subTest(name), patch('spread_tests_to_run.subprocess.run', run):
                args = dict(rules='main', changes=['snap/foo.go'])
                args.update(kwargs)
                selectors = stt.tests_to_run('openstack', 'ubuntu-24.04-64', ['tests/main/', 'tests/smoke/'], **args)
                self.assertEqual(selectors, ['openstack:ubuntu-24.04-64:tests/main/', 'openstack:ubuntu-24.04-64:tests/smoke/'])
        self.assertEqual(calls, [])

    def test_systems_all_and_none(self):
        run, _ = fake_filter(['tests/main/a'])
        with patch('spread_tests_to_run.subprocess.run', run):
            self.assertEqual(stt.tests_to_run('openstack', 'ALL', ['tests/...'], 'main', ['x'], pr=True),
                             ['openstack:tests/main/a'])
            self.assertEqual(stt.tests_to_run('openstack', 'ALL', ['tests/...']), ['openstack:tests/...'])
            self.assertEqual(stt.tests_to_run('openstack', 'NONE', ['tests/...'], 'main', ['x'], pr=True), [])

    def test_failed_tests_file_wins(self):
        with tempfile.NamedTemporaryFile('w', suffix='.txt') as f:
            f.write('openstack:ubuntu-24.04-64:tests/main/a\nopenstack:ubuntu-24.04-64:tests/main/b\n')
            f.flush()
            self.assertEqual(stt.tests_to_run('openstack', 'NONE', ['tests/...'], failed_tests_file=f.name),
                             ['openstack:ubuntu-24.04-64:tests/main/a', 'openstack:ubuntu-24.04-64:tests/main/b'])

    def test_spread_filter_failure(self):
        def run(cmd, capture_output, text, cwd):
            return subprocess.CompletedProcess(cmd, 1, "spread-filter: rules file 'x' does not exist", '')
        with patch('spread_tests_to_run.subprocess.run', run):
            with self.assertRaisesRegex(RuntimeError, 'does not exist'):
                stt.tests_to_run('openstack', 'ubuntu-24.04-64', ['tests/...'], 'missing', ['x'], pr=True)


if __name__ == '__main__':
    unittest.main()
