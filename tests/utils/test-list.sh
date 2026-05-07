#!/bin/bash

set -euo pipefail

test_list() {
    local pr="$1"
    local file_dir="$2"
    local files=$(gh pr view "$pr" --json files --jq '.files')
    local -a tests=()
    while read -r file; do
        filepath=$(jq -r '.path' <<< "$file")
        change_type=$(jq -r '.changeType' <<< "$file")
        if [[ "$filepath" =~ .*_test.go ]]; then
            if ! [[ "${tests[*]}" =~ "tests/unit/go" ]]; then
                tests+=("tests/unit/go")
            fi
            continue
        fi
        if [[ "$filepath" =~ ^tests/.* ]]; then
            echo "Need to evaluate items in tests/" >&2
            continue
        fi
        if ! [[ "$filepath" =~ .*go$ ]]; then
            echo "Need to evaluate non-go files" >&2
            continue
        fi
        if [[ "$change_type" == "MODIFIED" ]] && [[ "$filepath" =~ .*.go$ ]]; then
            while read -r match; do
                test_file=$(basename "$match")
                test_file="${test_file//--/\/}"
                if ! [[ " ${tests[*]} " =~ " $test_file " ]]; then
                    tests+=("$test_file")
                fi
            done < <(grep -lr "^$filepath$" "$file_dir")
        fi
        if [[ "$change_type" == "ADDED" ]] && [[ "$filepath" =~ .*.go$ ]]; then
            dirpath=$(dirname "$filepath")
            while read -r match; do
                test_file=$(basename "$match")
                test_file="${test_file//--/\/}"
                if ! [[ " ${tests[*]} " =~ " $test_file " ]]; then
                    tests+=("$test_file")
                fi
            done < <(grep -lr "^$dirpath/" "$file_dir")
        fi
    done < <(jq -c '.[]' <<< "$files")
    for test in "${tests[@]}"; do
        echo "$test"
    done
}

test_list "$@"