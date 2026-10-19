
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
    # documentation listing the tools, mentioned by a global helper
    'tests/lib/tools/README': 'docs-tool: a tool\n',
    'tests/lib/global-docs.sh': 'echo see README\n',
    'tests/lib/reset.sh': '. "$TESTSLIB"/global-docs.sh\n',
    'tests/lib/tools/docs-tool': 'echo docs\n',
    'tests/main/uses-docs-tool/task.yaml': 'execute: |\n    docs-tool\n',
    # two files with the same name
    'tests/lib/image.sh': 'echo image\n',
    'tests/lib/nested/image.sh': 'echo nested image\n',
    'tests/main/uses-image/task.yaml': 'execute: |\n    . "$TESTSLIB"/image.sh\n',
    'tests/main/uses-nested-image/task.yaml': 'execute: |\n    . "$TESTSLIB"/nested/image.sh\n',
    # copies of a tool used by its name
    'tests/bin/copied-tool': 'echo placeholder\n',
    'tests/lib/tools/copied-tool': 'echo placeholder\n',
    'tests/lib/external/ext-tools/tools/copied-tool': 'echo copied\n',
    'tests/main/uses-copied-tool/task.yaml': 'execute: |\n    copied-tool\n    "$TESTSTOOLS"/copied-tool\n',
    # an external project with its own tests
    'tests/lib/external/ext-tools/spread.yaml': 'suites:\n    tests/:\n        summary: own tests\n',
    'tests/lib/external/ext-tools/tests/ext-tool/task.yaml': 'execute: |\n    ext-tool\n',
    'tests/lib/external/ext-tools/tools/ext-tool': 'echo ext\n',
    'tests/main/uses-ext-tool/task.yaml': 'execute: |\n    ext-tool\n',
    # a chain of helpers longer than MAX_DEPTH
    'tests/lib/chain0.sh': 'echo chain0\n',
    'tests/lib/chain1.sh': '. "$TESTSLIB"/chain0.sh\n',
    'tests/lib/chain2.sh': '. "$TESTSLIB"/chain1.sh\n',
    'tests/lib/chain3.sh': '. "$TESTSLIB"/chain2.sh\n',
    'tests/lib/chain4.sh': '. "$TESTSLIB"/chain3.sh\n',
    'tests/main/uses-chain/task.yaml': 'execute: |\n    . "$TESTSLIB"/chain4.sh\n',
    # used through something built from it, not referenced by name
    'tests/lib/fakestore/store/store.go': 'package store\n',
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
        self.assertEqual(self.finder.users('tests/lib/tools/README'), frozenset())

    def test_users_ignores_docs(self):
        # the README mentions the tool and a global helper mentions the
        # README, which does not make the tool used by all tests
        self.assertEqual(self.finder.users('tests/lib/tools/docs-tool'), {'tests/main/uses-docs-tool'})

    def test_users_same_file_name(self):
        self.assertEqual(self.finder.users('tests/lib/image.sh'), {'tests/main/uses-image'})
        self.assertEqual(self.finder.users('tests/lib/nested/image.sh'), {'tests/main/uses-nested-image'})
        # references without a folder, or with the folder of a copy, count for every copy
        for path in ('tests/bin/copied-tool', 'tests/lib/tools/copied-tool',
                     'tests/lib/external/ext-tools/tools/copied-tool'):
            self.assertEqual(self.finder.users(path), {'tests/main/uses-copied-tool'}, path)

    def test_users_external_project(self):
        self.assertEqual(self.finder.users('tests/lib/external/ext-tools/tools/ext-tool'),
                         {'tests/main/uses-ext-tool'})
        self.assertEqual(self.finder.users('tests/lib/external/ext-tools/spread.yaml'), frozenset())
        self.assertEqual(self.finder.users('tests/lib/external/ext-tools/tests/ext-tool/task.yaml'), frozenset())

    def test_users_do_not_depend_on_earlier_calls(self):
        # chain0.sh is beyond MAX_DEPTH from the test, so its search is cut
        # short; that must not be cached for the helpers it went through
        self.assertEqual(self.finder.users('tests/lib/chain3.sh'), {'tests/main/uses-chain'})
        fresh = shared_test_users.SharedTestUsers(self.repo)
        self.assertEqual(fresh.users('tests/lib/chain0.sh'), frozenset())
        self.assertEqual(fresh.users('tests/lib/chain3.sh'), {'tests/main/uses-chain'})
        self.assertEqual(fresh.users('tests/lib/chain1.sh'), {'tests/main/uses-chain'})

    def test_report(self):
        report = self.finder.report({
            'modified': ['tests/lib/helper.sh', 'tests/main/uses-nothing/task.yaml', 'daemon/api.go',
                         'tests/lib/fakestore/store/store.go', 'tests/lib/README.md'],
            'added': [],
            'deleted': ['tests/lib/global.sh'],
        })
        self.assertEqual(report, {
            'tests/lib/helper.sh': {'all': False, 'tests': ['tests/main/uses-helper', 'tests/main/uses-wrapper']},
            'tests/lib/fakestore/store/store.go': {'all': False, 'tests': [], 'unresolved': True},
            'tests/lib/README.md': {'all': False, 'tests': []},
            'tests/lib/global.sh': {'all': True},
        })

    def test_rewrite(self):
        rewritten = self.finder.rewrite({
            'modified': ['daemon/api.go', 'tests/lib/helper.sh', 'tests/main/uses-helper/task.yaml',
                         'tests/lib/README.md', 'tests/lib/external/ext-tools/tests/ext-tool/task.yaml'],
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
            # no reference found: kept so the service runs everything
            'added': ['tests/lib/unused.sh'],
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
