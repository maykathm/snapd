#!/usr/bin/env python3

'''
Finds the spread tests that use shared test files.

A change to a file inside a spread test's folder (tests/<suite>/<test>/...)
only affects that test, but a change to a shared file under tests/ (helpers in
tests/lib, test snaps in tests/lib/snaps, tools, ...) affects every test that
uses it. This utility finds those users by searching the checkout for
references to the shared file:

- references from a test's folder select that test
- references from another shared file are followed to that file's users
- references from a suite's section of spread.yaml select every test in the suite
- references from anywhere else in spread.yaml, or from the helpers that run
  around every test (tests/lib/prepare.sh, prepare-restore.sh, reset.sh), mean
  the file is used by all tests

When other files under tests/ have the same name, references qualified with
the folder of one of them only are not counted: $TESTSLIB/image.sh refers to
tests/lib/image.sh, not tests/lib/nested/image.sh. References without a folder
count for all of them. Documentation (README files, *.md) and the own tests,
spread.yaml and CI of the projects under tests/lib/external are not used by
any test.

It is meant to run in CI, in the checkout of the change being tested, before
asking the test-execution-lister service which tests to run. With --rewrite it
prints the changed files with every shared file replaced by the task.yaml of
each test that uses it, so the service selects those tests; files used by all
tests, and files no reference to was found for (e.g. the fakestore sources,
used through the binary built from them), are kept, so the service still runs
everything for them.
'''

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Callable, Optional

# helpers that run before or after every test
GLOBAL_HELPERS = (
    'tests/lib/prepare.sh',
    'tests/lib/prepare-restore.sh',
    'tests/lib/reset.sh',
)
SPREAD_YAML = 'spread.yaml'
CHANGE_KEYS = ('modified', 'added', 'deleted')
# how many levels of shared files referencing shared files are followed
MAX_DEPTH = 3
EXTERNAL = 'tests/lib/external/'
# parts of the projects under tests/lib/external that only serve the project
# itself and are not used by snapd's tests
EXTERNAL_OWN = ('tests/', 'spread.yaml', '.github/')


def _reference_pattern(token: str) -> re.Pattern:
    # the token as a whole name: not part of a longer name such as
    # helper.sh.orig or other-helper.sh
    return re.compile(r'(?<![\w.-])' + re.escape(token) + r'(?![\w-]|\.\w)')


# folder names given by the variables used in tests to refer to shared files
_VARIABLE_FOLDERS = {'TESTSLIB': 'lib', 'TESTSTOOLS': 'tools'}
# the folder a reference is qualified with: ".../<folder>/" or "$VAR/"
_QUALIFIER = re.compile(r'(?:\$\{?(\w+)\}?"?|([\w.-]+))/$')


def _qualifier(before: str) -> Optional[str]:
    m = _QUALIFIER.search(before[-128:])
    if not m:
        return None
    if m.group(1):
        return _VARIABLE_FOLDERS.get(m.group(1))
    return m.group(2)


# tells whether a text refers to a shared file
Matcher = Callable[[str], bool]


def is_doc(path: str) -> bool:
    name = path.rsplit('/', 1)[-1]
    return name.upper().startswith('README') or name.endswith('.md')


def is_external_own(path: str) -> bool:
    '''Returns whether the path only serves an external project itself.'''
    if not path.startswith(EXTERNAL):
        return False
    parts = path[len(EXTERNAL):].split('/', 1)
    return len(parts) == 2 and parts[1].startswith(EXTERNAL_OWN)


_SUITE_LINE = re.compile(r'^    (tests/[^\s:]+)/:\s*$')
_TOP_LEVEL_LINE = re.compile(r'^[A-Za-z_-][^:]*:')


class SharedTestUsers:
    '''Finds the tests that use shared files in a snapd checkout.'''

    def __init__(self, repo: str):
        self.repo = repo
        self.spread_yaml = self._read(SPREAD_YAML).splitlines()
        self.suites = self._suites()
        self._folders_by_name = self._folders_by_file_name()
        # only results of searches that were not cut short (by MAX_DEPTH or
        # a cycle) are cached, so a result does not depend on earlier calls
        self._cache: dict[str, Optional[frozenset[str]]] = {}

    def _folders_by_file_name(self) -> dict[str, set[str]]:
        '''Returns the folders of the files under tests/ by file name.'''
        result = subprocess.run(['git', '-C', self.repo, 'ls-files', '--', 'tests'],
                                capture_output=True, text=True, check=True)
        folders: dict[str, set[str]] = {}
        for path in result.stdout.splitlines():
            folder, _, name = path.rpartition('/')
            folders.setdefault(name, set()).add(folder)
        return folders

    def _matcher(self, path: str, token: str) -> Matcher:
        '''
        Returns the matcher for references to the path. When the token is the
        file name and other files under tests/ have the same name, references
        qualified with the folder of one of those other files only (such as
        nested/image.sh or $TESTSLIB/image.sh for tests/lib/image.sh and
        tests/lib/nested/image.sh) are not counted. References without a
        folder are counted for all of them.
        '''
        pattern = _reference_pattern(token)
        folder, _, name = path.rpartition('/')
        own = folder.rpartition('/')[2]
        others = {f.rpartition('/')[2] for f in self._folders_by_name.get(name, set())} - {own}
        if token != name or not others:
            return lambda text: bool(pattern.search(text))

        def matches(text: str) -> bool:
            return any(_qualifier(text[:m.start()]) not in others for m in pattern.finditer(text))
        return matches

    def _read(self, path: str) -> str:
        with open(os.path.join(self.repo, path), encoding='utf-8') as f:
            return f.read()

    def _suites(self) -> list[str]:
        suites = []
        in_suites = False
        for line in self.spread_yaml:
            if _TOP_LEVEL_LINE.match(line):
                in_suites = line.startswith('suites:')
            elif in_suites:
                m = _SUITE_LINE.match(line)
                if m:
                    suites.append(m.group(1))
        # longest first so nested suites (tests/nested/core) win over parents
        return sorted(suites, key=len, reverse=True)

    def test_dir(self, path: str) -> Optional[str]:
        '''Returns the test folder that contains the path, if any.'''
        for suite in self.suites:
            if path.startswith(suite + '/'):
                rest = path[len(suite) + 1:]
                if '/' in rest:
                    return f'{suite}/{rest.split("/", 1)[0]}'
                return None
        return None

    def suite_tests(self, suite: str) -> set[str]:
        '''Returns the test folders of a suite, i.e. those with a task.yaml.'''
        suite_path = os.path.join(self.repo, suite)
        if not os.path.isdir(suite_path):
            return set()
        return {
            f'{suite}/{entry}'
            for entry in os.listdir(suite_path)
            if os.path.isfile(os.path.join(suite_path, entry, 'task.yaml'))
        }

    @staticmethod
    def token(path: str) -> str:
        '''
        Returns the name other files use to refer to a shared file: the snap
        name for test snaps, the tool name for tools, else the file name.
        '''
        parts = path.split('/')
        if path.startswith('tests/lib/snaps/') and len(parts) > 4:
            if parts[3] == 'store' and len(parts) > 5:
                return parts[4]
            return parts[3]
        if path.startswith('tests/lib/tools/') and len(parts) > 3:
            return parts[3]
        return parts[-1]

    def _own_files_prefix(self, path: str) -> str:
        '''Files that are part of the same shared item, e.g. a test snap's folder.'''
        parts = path.split('/')
        if path.startswith('tests/lib/snaps/') and len(parts) > 4:
            depth = 5 if parts[3] == 'store' and len(parts) > 5 else 4
            return '/'.join(parts[:depth]) + '/'
        return path

    def _grep(self, path: str, token: str) -> list[str]:
        result = subprocess.run(
            ['git', '-C', self.repo, 'grep', '-l', '-F', '-e', token, '--', 'tests', SPREAD_YAML],
            capture_output=True, text=True)
        if result.returncode not in (0, 1):
            raise RuntimeError(f'git grep failed: {result.stderr.strip()}')
        matches = self._matcher(path, token)
        hits = []
        for hit in result.stdout.splitlines():
            try:
                content = self._read(hit)
            except (OSError, UnicodeDecodeError):
                continue
            if matches(content):
                hits.append(hit)
        return hits

    def _spread_yaml_users(self, matches: Matcher) -> Optional[set[str]]:
        '''
        Returns the tests of the suites whose section of spread.yaml refers to
        the shared file, or None if it is referred to outside of any suite.
        '''
        users: set[str] = set()
        top = None
        suite = None
        for line in self.spread_yaml:
            if _TOP_LEVEL_LINE.match(line):
                top = line.split(':', 1)[0]
                suite = None
                continue
            if top == 'suites':
                m = _SUITE_LINE.match(line)
                if m:
                    suite = m.group(1)
                    continue
            if not matches(line):
                continue
            if top == 'suites' and suite:
                users |= self.suite_tests(suite)
            else:
                return None
        return users

    @staticmethod
    def not_used(path: str) -> bool:
        '''Returns whether the path is known not to be used by any test.'''
        return is_doc(path) or is_external_own(path)

    def users(self, path: str) -> Optional[frozenset[str]]:
        '''
        Returns the test folders that use a shared file, or None if it is used
        by all tests.
        '''
        return self._users(path, 0, frozenset())[0]

    def _users(self, path: str, depth: int, seen: frozenset[str]) -> tuple[Optional[frozenset[str]], bool]:
        '''
        Returns the users of the path and whether the search was complete, i.e.
        not cut short by MAX_DEPTH or a cycle.
        '''
        if path in self._cache:
            return self._cache[path], True
        if self.not_used(path):
            return frozenset(), True
        seen = seen | {path}
        token = self.token(path)
        own = self._own_files_prefix(path)
        found: set[str] = set()
        complete = True
        for hit in self._grep(path, token):
            if hit == path or hit.startswith(own) or self.not_used(hit):
                continue
            if hit in GLOBAL_HELPERS:
                self._cache[path] = None
                return None, True
            if hit == SPREAD_YAML:
                suite_users = self._spread_yaml_users(self._matcher(path, token))
                if suite_users is None:
                    self._cache[path] = None
                    return None, True
                found |= suite_users
                continue
            test = self.test_dir(hit)
            if test:
                found.add(test)
            elif self.token(hit) == token:
                # a file with the same name, e.g. another copy of a tool
                continue
            elif hit in seen or depth >= MAX_DEPTH:
                complete = False
            else:
                inner, inner_complete = self._users(hit, depth + 1, seen)
                if inner is None:
                    self._cache[path] = None
                    return None, True
                found |= inner
                complete = complete and inner_complete
        result = frozenset(found)
        if complete:
            self._cache[path] = result
        return result, complete

    def is_shared(self, path: str) -> bool:
        return path.startswith('tests/') and self.test_dir(path) is None

    def report(self, changed_files: dict[str, list[str]]) -> dict[str, dict]:
        '''
        Returns the users of each shared file in the changes. Files no
        reference to was found for, that are not known to be unused, are
        marked as unresolved.
        '''
        out = {}
        for key in CHANGE_KEYS:
            for path in changed_files.get(key, []):
                if not self.is_shared(path):
                    continue
                users = self.users(path)
                if users is None:
                    out[path] = {'all': True}
                else:
                    out[path] = {'all': False, 'tests': sorted(users)}
                    if not users and not self.not_used(path):
                        out[path]['unresolved'] = True
        return out

    def rewrite(self, changed_files: dict[str, list[str]]) -> dict[str, list[str]]:
        '''
        Returns the changed files with each shared file replaced by the
        task.yaml of every test that uses it. Shared files used by all tests,
        or that no reference to was found for, are kept as they are; files
        known not to be used by any test are dropped.
        '''
        out: dict[str, list[str]] = {key: [] for key in CHANGE_KEYS}
        for key in CHANGE_KEYS:
            for path in changed_files.get(key, []):
                if not self.is_shared(path):
                    target, paths = key, [path]
                else:
                    users = self.users(path)
                    if users is None or (not users and not self.not_used(path)):
                        target, paths = key, [path]
                    else:
                        target, paths = 'modified', [f'{test}/task.yaml' for test in sorted(users)]
                for p in paths:
                    if p not in out[target]:
                        out[target].append(p)
        return out


def changed_files_from_git(repo: str, base: str, head: str) -> dict[str, list[str]]:
    result = subprocess.run(
        ['git', '-C', repo, 'diff', '--name-status', '-M', f'{base}...{head}'],
        capture_output=True, text=True, check=True)
    files: dict[str, list[str]] = {key: [] for key in CHANGE_KEYS}
    for line in result.stdout.splitlines():
        status, *paths = line.split('\t')
        if status == 'M':
            files['modified'].append(paths[0])
        elif status == 'A':
            files['added'].append(paths[0])
        elif status == 'D':
            files['deleted'].append(paths[0])
        else:
            # renames and copies: the old path goes away and the new one appears
            files['deleted'].append(paths[0])
            files['added'].append(paths[-1])
    return files


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', default='.', help='path to the snapd checkout (default: .)')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--changed-files', type=argparse.FileType('r', encoding='utf-8'),
                        help='json file with modified, added and deleted lists of paths ("-" for stdin)')
    source.add_argument('--base', help='compute the changed files as git diff <base>...<head>')
    parser.add_argument('--head', default='HEAD', help='head revision when using --base (default: HEAD)')
    parser.add_argument('--rewrite', action='store_true',
                        help='print the changed files with shared files replaced by the task.yaml of their users')
    args = parser.parse_args()

    if args.base:
        changed = changed_files_from_git(args.repo, args.base, args.head)
    else:
        changed = json.load(args.changed_files)

    finder = SharedTestUsers(args.repo)
    result = finder.rewrite(changed) if args.rewrite else finder.report(changed)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    print()


if __name__ == '__main__':
    main()
