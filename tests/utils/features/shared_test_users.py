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

With a base revision, a changed tool with subcommands (a shell script under
tests/ dispatching on its first argument, with a case branch per subcommand or
by calling the function named after it) only counts references that use the
subcommands the change affects: the scripts are parsed with shfmt, the changed
lines are mapped to the functions or dispatch branches they are in, functions
calling affected functions are added, and a reference such as
"lxd-state launch" counts only if "launch" is affected or is not one of the
tool's subcommands. Changes outside of functions and dispatch branches (other
than blank lines and comments) affect the whole tool, as does any change when
shfmt is not installed or cannot parse the tool.

It is meant to run in CI, in the checkout of the change being tested, before
asking the test-selector service which tests to run. With --rewrite it
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


# prints a tool's usage: changing it affects none of its subcommands, and
# references such as "tool --help" count anyway as they use no subcommand
_HELP_FUNCTION = 'show_help'
_warned_no_shfmt = False


def _is_code(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith('#')


def _line(pos: dict) -> int:
    '''The 0-based line index of a shfmt position.'''
    return pos['Line'] - 1


def _literal(word: dict) -> Optional[str]:
    '''The value of a shell word made only of literal text, quoted or not.'''
    value = ''
    for part in word.get('Parts', []):
        if part['Type'] in ('Lit', 'SglQuoted'):
            value += part['Value']
        elif part['Type'] == 'DblQuoted' and all(p['Type'] == 'Lit' for p in part.get('Parts', [])):
            value += ''.join(p['Value'] for p in part.get('Parts', []))
        else:
            return None
    return value


def _nodes(node, skip=()):
    '''Yields the syntax tree nodes under node, not descending into those in skip.'''
    if isinstance(node, dict):
        if any(node is s for s in skip):
            return
        yield node
        for value in node.values():
            yield from _nodes(value, skip)
    elif isinstance(node, list):
        for value in node:
            yield from _nodes(value, skip)


def _calls(node, skip=()) -> list[dict]:
    return [n for n in _nodes(node, skip) if n.get('Type') == 'CallExpr' and n.get('Args')]


def _call_names(node, skip=()) -> set[str]:
    '''The commands (and functions) called under node, when literal.'''
    return {name for call in _calls(node, skip) if (name := _literal(call['Args'][0]))}


def _top_level_cases(node) -> list[dict]:
    '''The case statements under node that are not inside another case statement.'''
    if isinstance(node, dict):
        if node.get('Type') == 'CaseClause':
            return [node]
        return [case for value in node.values() for case in _top_level_cases(value)]
    if isinstance(node, list):
        return [case for value in node for case in _top_level_cases(value)]
    return []


class Dispatch:
    '''How a tool dispatches its subcommands.'''

    def __init__(self, subcommands: dict[str, list[tuple[int, int]]], generic: bool,
                 branch_calls: dict[str, set[str]], outside_calls: set[str]):
        # subcommand: (first, last) line indexes of its case branches, if any
        # (e.g. one parsing the arguments and one running the subcommand)
        self.subcommands = subcommands
        # subcommands run the function named after them ("-" becomes "_")
        self.generic = generic
        # what each subcommand's case branch calls
        self.branch_calls = branch_calls
        # what main calls outside of the dispatch branches
        self.outside_calls = outside_calls


class ShellScript:
    '''The functions and subcommand dispatch of a shell script, parsed with shfmt.'''

    def __init__(self, ast: dict):
        functions = {}
        calls = {}
        for stmt in ast.get('Stmts', []):
            cmd = stmt.get('Cmd', {})
            if cmd.get('Type') == 'FuncDecl':
                name = cmd['Name']['Value']
                functions[name] = (_line(cmd['Pos']), _line(cmd['End']))
                calls[name] = _call_names(cmd['Body'])
        # name: (first, last) line index, from the declaration to the closing brace
        self.functions: dict[str, tuple[int, int]] = functions
        # name: the commands and functions it calls
        self.calls: dict[str, set[str]] = calls
        self.dispatch = self._dispatch(ast)

    @staticmethod
    def parse(text: str) -> Optional['ShellScript']:
        '''Returns the parsed script, or None if it cannot be parsed (or shfmt is missing).'''
        global _warned_no_shfmt
        try:
            result = subprocess.run(['shfmt', '-ln', 'bash', '--to-json'], input=text, capture_output=True, text=True)
        except FileNotFoundError:
            if not _warned_no_shfmt:
                print('shared_test_users: shfmt not found, changed tools are not narrowed to subcommands',
                      file=sys.stderr)
                _warned_no_shfmt = True
            return None
        if result.returncode != 0:
            return None
        return ShellScript(json.loads(result.stdout))

    def owner(self, index: int) -> Optional[str]:
        '''The function the line index is in, if any.'''
        return next((name for name, (first, last) in self.functions.items() if first <= index <= last), None)

    def _dispatch(self, ast: dict) -> Optional[Dispatch]:
        main = next((stmt['Cmd'] for stmt in ast.get('Stmts', [])
                     if stmt.get('Cmd', {}).get('Type') == 'FuncDecl' and stmt['Cmd']['Name']['Value'] == 'main'), None)
        if main is None:
            return None
        if any(_literal(c['Args'][0]) == 'tr' and [_literal(a) for a in c['Args'][1:3]] == ['-', '_']
               for c in _calls(main['Body'])):
            names = {name.replace('_', '-'): [] for name in self.functions if name not in ('main', _HELP_FUNCTION)}
            return Dispatch(names, True, {}, _call_names(main['Body']))

        # the case statements of main not nested in another one: a subcommand
        # can have a branch in several of them
        subcommands: dict[str, list[tuple[int, int]]] = {}
        branch_calls: dict[str, set[str]] = {}
        branches = []
        for case in _top_level_cases(main['Body']):
            for item in case.get('Items', []):
                names = [_literal(p) for p in item.get('Patterns', [])]
                names = [n for n in names if n and not n.startswith('-') and '*' not in n]
                if not names:
                    continue
                branches.append(item)
                for name in names:
                    subcommands.setdefault(name, []).append((_line(item['Pos']), _line(item['End'])))
                    branch_calls.setdefault(name, set()).update(_call_names(item.get('Stmts', [])))
        if not subcommands:
            return None
        return Dispatch(subcommands, False, branch_calls, _call_names(main['Body'], skip=branches))


def affected_subcommands(old: str, new: str, removed: list[int], added: list[int]) -> Optional[set[str]]:
    '''
    Returns the subcommands of a tool affected by a change, given the old and
    new content and the indexes of the removed (old) and added (new) lines, or
    None if the change affects the whole tool or the tool has no subcommands.
    '''
    affected_functions: set[str] = set()
    affected: set[str] = set()
    scripts = []
    for text, changed in ((old, removed), (new, added)):
        script = ShellScript.parse(text)
        if script is None or script.dispatch is None:
            return None
        scripts.append(script)
        lines = text.splitlines()
        for index in changed:
            if index >= len(lines) or not _is_code(lines[index]):
                continue
            owner = script.owner(index)
            if owner is None:
                return None
            if owner == _HELP_FUNCTION:
                continue
            if owner != 'main':
                affected_functions.add(owner)
                continue
            branch = [sub for sub, spans in script.dispatch.subcommands.items()
                      if any(first <= index <= last for first, last in spans)]
            if not branch:
                return None
            affected.update(branch)

    # functions calling affected functions are affected too
    script = scripts[1]
    while True:
        callers = {name for name, calls in script.calls.items()
                   if name not in ('main', _HELP_FUNCTION) and calls & affected_functions} - affected_functions
        if not callers:
            break
        affected_functions |= callers
    if script.dispatch.outside_calls & affected_functions:
        # main calls an affected function outside of the dispatch branches
        return None

    for sub in script.dispatch.subcommands:
        if script.dispatch.generic:
            if sub.replace('-', '_') in affected_functions:
                affected.add(sub)
        elif script.dispatch.branch_calls.get(sub, set()) & affected_functions:
            affected.add(sub)
    return affected


class SubcommandFilter:
    '''The subcommands of a changed tool, and those the change affects.'''

    def __init__(self, known: set[str], affected: set[str]):
        self.known = known
        self.affected = affected

    def counts(self, after: str) -> bool:
        '''Whether a reference to the tool followed by the text after counts.'''
        m = re.match(r'["\']?\s+([\w-]+)', after)
        if not m or m.group(1) not in self.known:
            # no subcommand, or not a literal one: the reference may use any
            return True
        return m.group(1) in self.affected


_SUITE_LINE = re.compile(r'^    (tests/[^\s:]+)/:\s*$')
_TOP_LEVEL_LINE = re.compile(r'^[A-Za-z_-][^:]*:')


class SharedTestUsers:
    '''Finds the tests that use shared files in a snapd checkout.'''

    def __init__(self, repo: str, base: Optional[str] = None):
        self.repo = repo
        # revision the checkout is compared to, to narrow changed tools to
        # the subcommands the change affects
        self.base = base
        self._merge_base: Optional[str] = None
        self._filters: dict[str, Optional[SubcommandFilter]] = {}
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
        qualified = token == name and others
        subcommands = self.subcommand_filter(path)
        if not qualified and subcommands is None:
            return lambda text: bool(pattern.search(text))

        def matches(text: str) -> bool:
            for m in pattern.finditer(text):
                if qualified and _qualifier(text[:m.start()]) in others:
                    continue
                if subcommands is not None and not subcommands.counts(text[m.end():m.end() + 64]):
                    continue
                return True
            return False
        return matches

    def subcommand_filter(self, path: str) -> Optional[SubcommandFilter]:
        '''
        Returns the subcommands of a tool changed since the base revision and
        those the change affects, or None if references to the path all count.
        '''
        if self.base is None:
            return None
        if path not in self._filters:
            self._filters[path] = self._compute_subcommand_filter(path)
        return self._filters[path]

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(['git', '-C', self.repo, *args], capture_output=True, text=True)

    def _compute_subcommand_filter(self, path: str) -> Optional[SubcommandFilter]:
        if self._merge_base is None:
            result = self._git('merge-base', self.base, 'HEAD')
            if result.returncode != 0:
                raise RuntimeError(f'git merge-base failed: {result.stderr.strip()}')
            self._merge_base = result.stdout.strip()
        old = self._git('show', f'{self._merge_base}:{path}')
        if old.returncode != 0 or not os.path.isfile(os.path.join(self.repo, path)):
            # added or deleted: the whole tool is affected
            return None
        try:
            new_text = self._read(path)
        except UnicodeDecodeError:
            return None
        diff = self._git('diff', '-U0', self._merge_base, '--', path)
        removed, added = [], []
        for line in diff.stdout.splitlines():
            m = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
            if m:
                old_start, old_count = int(m.group(1)), int(m.group(2) or 1)
                new_start, new_count = int(m.group(3)), int(m.group(4) or 1)
                removed += range(old_start - 1, old_start - 1 + old_count)
                added += range(new_start - 1, new_start - 1 + new_count)
        if not removed and not added:
            return None
        affected = affected_subcommands(old.stdout, new_text, removed, added)
        if affected is None:
            return None
        return SubcommandFilter(set(ShellScript.parse(new_text).dispatch.subcommands), affected)

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

    def _unresolved(self, path: str, users: frozenset[str]) -> bool:
        '''
        Whether no user was found for a path that may still be used: not known
        to be unused, and not a tool whose affected subcommands nothing uses.
        '''
        return not users and not self.not_used(path) and self.subcommand_filter(path) is None

    def report(self, changed_files: dict[str, list[str]]) -> dict[str, dict]:
        '''
        Returns the users of each shared file in the changes. Files no
        reference to was found for, that are not known to be unused, are
        marked as unresolved. Changed tools narrowed to the subcommands the
        change affects list them.
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
                    if self._unresolved(path, users):
                        out[path]['unresolved'] = True
                subcommands = self.subcommand_filter(path)
                if subcommands is not None:
                    out[path]['subcommands'] = sorted(subcommands.affected)
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
                    if users is None or self._unresolved(path, users):
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
    parser.add_argument('--changed-files', type=argparse.FileType('r', encoding='utf-8'),
                        help='json file with modified, added and deleted lists of paths ("-" for stdin)')
    parser.add_argument('--base',
                        help='revision the change is based on: the changed files default to git diff <base>...<head>, '
                             'and changed tools are narrowed to the subcommands the change affects')
    parser.add_argument('--head', default='HEAD', help='head revision when using --base (default: HEAD)')
    parser.add_argument('--rewrite', action='store_true',
                        help='print the changed files with shared files replaced by the task.yaml of their users')
    args = parser.parse_args()
    if not args.changed_files and not args.base:
        parser.error('one of --changed-files or --base is required')

    if args.changed_files:
        changed = json.load(args.changed_files)
    else:
        changed = changed_files_from_git(args.repo, args.base, args.head)

    finder = SharedTestUsers(args.repo, base=args.base)
    result = finder.rewrite(changed) if args.rewrite else finder.report(changed)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    print()


if __name__ == '__main__':
    main()
