
import os
import subprocess
import sys
import tempfile
import unittest
# To ensure the unit test can be run from any point in the filesystem,
# add parent folder to path to permit relative imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import shared_test_users


SPREAD_YAML = '''project: snapd

prepare: |
    "$TESTSLIB"/prepare-restore.sh --prepare-project

suites:
    tests/main/:
        summary: Full-system tests for snapd
        prepare-each: |
            suite-helper.sh
    tests/nested/core/:
        summary: Nested tests
        prepare: |
            nested-only-tool
'''

FILES = {
    'spread.yaml': SPREAD_YAML,
    'tests/lib/prepare-restore.sh': '. "$TESTSLIB"/global.sh\n',
    'tests/lib/global.sh': 'echo global\n',
    'tests/lib/helper.sh': 'echo helper\n',
    'tests/lib/wrapper.sh': '. "$TESTSLIB"/helper.sh\n',
    'tests/lib/suite-helper.sh': 'echo suite\n',
    'tests/lib/unused.sh': 'echo unused\n',
    'tests/lib/tools/nested-only-tool': 'echo nested\n',
    'tests/lib/snaps/test-snapd-foo/meta/snap.yaml': 'name: test-snapd-foo\n',
    'tests/lib/snaps/test-snapd-foo/bin/foo': 'echo test-snapd-foo\n',
    'tests/lib/snaps/store/test-snapd-store/meta/snap.yaml': 'name: test-snapd-store\n',
    'tests/main/uses-helper/task.yaml': 'execute: |\n    . "$TESTSLIB"/helper.sh\n',
    'tests/main/uses-wrapper/task.yaml': 'execute: |\n    . "$TESTSLIB"/wrapper.sh\n',
    'tests/main/uses-snap/task.yaml': 'execute: |\n    "$TESTSTOOLS"/snaps-state install-local test-snapd-foo\n',
    'tests/main/uses-store-snap/task.yaml': 'execute: |\n    snap install test-snapd-store\n',
    'tests/main/uses-nothing/task.yaml': 'execute: |\n    true\n',
    'tests/main/uses-helper-two/task.yaml': 'execute: |\n    . "$TESTSLIB"/helper.sh.orig\n',
    'tests/nested/core/nested-test/task.yaml': 'execute: |\n    true\n',
}


class TestSharedTestUsers(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        for path, content in FILES.items():
            full = os.path.join(self.repo, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w', encoding='utf-8') as f:
                f.write(content)
        subprocess.run(['git', 'init', '-q', self.repo], check=True)
        subprocess.run(['git', '-C', self.repo, 'add', '.'], check=True)
        self.finder = shared_test_users.SharedTestUsers(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_suites_from_spread_yaml(self):
        self.assertEqual(self.finder.suites, ['tests/nested/core', 'tests/main'])

    def test_test_dir(self):
        self.assertEqual(self.finder.test_dir('tests/main/uses-helper/task.yaml'), 'tests/main/uses-helper')
        self.assertEqual(self.finder.test_dir('tests/nested/core/nested-test/a/b.sh'), 'tests/nested/core/nested-test')
        self.assertIsNone(self.finder.test_dir('tests/lib/helper.sh'))
        self.assertIsNone(self.finder.test_dir('tests/main/README.md'))

    def test_token(self):
        self.assertEqual(self.finder.token('tests/lib/helper.sh'), 'helper.sh')
        self.assertEqual(self.finder.token('tests/lib/tools/nested-only-tool'), 'nested-only-tool')
        self.assertEqual(self.finder.token('tests/lib/snaps/test-snapd-foo/bin/foo'), 'test-snapd-foo')
        self.assertEqual(self.finder.token('tests/lib/snaps/store/test-snapd-store/meta/snap.yaml'), 'test-snapd-store')

    def test_users_direct_and_transitive(self):
        # helper.sh is used directly and through wrapper.sh; helper.sh.orig is a different file
        self.assertEqual(self.finder.users('tests/lib/helper.sh'),
                         {'tests/main/uses-helper', 'tests/main/uses-wrapper'})

    def test_users_of_test_snaps(self):
        self.assertEqual(self.finder.users('tests/lib/snaps/test-snapd-foo/bin/foo'), {'tests/main/uses-snap'})
        self.assertEqual(self.finder.users('tests/lib/snaps/store/test-snapd-store/meta/snap.yaml'),
                         {'tests/main/uses-store-snap'})

    def test_users_global(self):
        # used by a helper that runs around every test, or outside the suites in spread.yaml
        self.assertIsNone(self.finder.users('tests/lib/global.sh'))
        self.assertIsNone(self.finder.users('tests/lib/prepare-restore.sh'))

    def test_users_from_suite_section(self):
        self.assertEqual(self.finder.users('tests/lib/tools/nested-only-tool'), {'tests/nested/core/nested-test'})
        self.assertEqual(self.finder.users('tests/lib/suite-helper.sh'), self.finder.suite_tests('tests/main'))

    def test_users_unused_and_docs(self):
        self.assertEqual(self.finder.users('tests/lib/unused.sh'), frozenset())
        self.assertEqual(self.finder.users('tests/lib/README.md'), frozenset())

    def test_report(self):
        report = self.finder.report({
            'modified': ['tests/lib/helper.sh', 'tests/main/uses-nothing/task.yaml', 'daemon/api.go'],
            'added': [],
            'deleted': ['tests/lib/global.sh'],
        })
        self.assertEqual(report, {
            'tests/lib/helper.sh': {'all': False, 'tests': ['tests/main/uses-helper', 'tests/main/uses-wrapper']},
            'tests/lib/global.sh': {'all': True},
        })

    def test_rewrite(self):
        rewritten = self.finder.rewrite({
            'modified': ['daemon/api.go', 'tests/lib/helper.sh', 'tests/main/uses-helper/task.yaml'],
            'added': ['tests/lib/snaps/test-snapd-foo/bin/foo', 'tests/lib/unused.sh'],
            'deleted': ['tests/lib/global.sh'],
        })
        self.assertEqual(rewritten, {
            'modified': [
                'daemon/api.go',
                'tests/main/uses-helper/task.yaml',
                'tests/main/uses-wrapper/task.yaml',
                'tests/main/uses-snap/task.yaml',
            ],
            'added': [],
            'deleted': ['tests/lib/global.sh'],
        })

    def test_changed_files_from_git(self):
        subprocess.run(['git', '-C', self.repo, '-c', 'user.name=t', '-c', 'user.email=t@t',
                        'commit', '-qm', 'base'], check=True)
        os.remove(os.path.join(self.repo, 'tests/lib/unused.sh'))
        with open(os.path.join(self.repo, 'tests/lib/helper.sh'), 'a', encoding='utf-8') as f:
            f.write('echo more\n')
        with open(os.path.join(self.repo, 'tests/lib/new.sh'), 'w', encoding='utf-8') as f:
            f.write('echo new\n')
        subprocess.run(['git', '-C', self.repo, 'add', '-A'], check=True)
        subprocess.run(['git', '-C', self.repo, '-c', 'user.name=t', '-c', 'user.email=t@t',
                        'commit', '-qm', 'change'], check=True)
        self.assertEqual(shared_test_users.changed_files_from_git(self.repo, 'HEAD~1', 'HEAD'), {
            'modified': ['tests/lib/helper.sh'],
            'added': ['tests/lib/new.sh'],
            'deleted': ['tests/lib/unused.sh'],
        })


if __name__ == '__main__':
    unittest.main()
