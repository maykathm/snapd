#!/usr/bin/env python3

'''
Prints the spread tests to run for a spread-tests.yaml job, as the
space-separated list of spread selectors (BACKEND:SYSTEM:TASK) the job passes
to spread. Used by the "Setup run tests variable" step, and locally to see
what a job would run:

- with a failed tests file (a re-run of failed tests), its content
- with systems NONE, nothing
- for pull requests with rules and changed files, the tasks spread-filter
  selects with tests/lib/spread/rules/<rules>.yaml for the changes
- otherwise, and when running nested tests, every task, for every system
  (systems ALL uses the backend alone as prefix)
'''

import argparse
import os
import subprocess
import sys

SPREAD_FILTER = 'tests/lib/external/snapd-testing-tools/utils/spread-filter'
RULES_DIR = 'tests/lib/spread/rules'


def spread_filter(repo, rules, prefix, changes, tasks):
    cmd = [os.path.join(repo, SPREAD_FILTER), '-r', os.path.join(repo, RULES_DIR, rules + '.yaml'), '-p', prefix]
    for change in changes:
        cmd += ['-c', change]
    cmd += ['-t', ' '.join(tasks)]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo)
    if result.returncode != 0:
        raise RuntimeError('spread-filter failed: {}'.format((result.stdout + result.stderr).strip()))
    return result.stdout.split()


def tests_to_run(backend, systems, tasks, rules='', changes=(), pr=False, run_nested=False,
                 failed_tests_file=None, repo='.'):
    '''Returns the spread selectors to run, in order.'''
    if failed_tests_file:
        with open(failed_tests_file, encoding='utf-8') as f:
            return f.read().split()
    if systems.strip() == 'NONE':
        return []
    prefixes = [backend] if systems.strip() == 'ALL' else [backend + ':' + system for system in systems.split()]

    # tests are only filtered by the changes for pull requests; with the
    # "Run nested" label all nested tests run
    filtered = pr and not run_nested and rules and changes
    selectors = []
    for prefix in prefixes:
        if filtered:
            selectors += spread_filter(repo, rules, prefix, changes, tasks)
        else:
            selectors += [prefix + ':' + task for task in tasks]
    return selectors


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--backend', required=True, help='spread backend')
    parser.add_argument('--systems', required=True, help='space-separated spread systems, ALL or NONE')
    parser.add_argument('--tasks', required=True, help='space or newline separated spread tasks')
    parser.add_argument('--rules', default='', help='rules file name under {} (without .yaml)'.format(RULES_DIR))
    parser.add_argument('--change', action='append', default=[], help='changed file; can be repeated')
    parser.add_argument('--pr', action='store_true', help='the job runs for a pull request')
    parser.add_argument('--run-nested', action='store_true', help='the pull request has the "Run nested" label')
    parser.add_argument('--failed-tests-file', help='file listing the tests that failed in the previous attempt')
    parser.add_argument('--repo', default='.', help='snapd checkout (default: .)')
    args = parser.parse_args()

    try:
        selectors = tests_to_run(args.backend, args.systems, args.tasks.split(), args.rules, args.change,
                                 args.pr, args.run_nested, args.failed_tests_file, args.repo)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    print(' '.join(selectors))


if __name__ == '__main__':
    main()
