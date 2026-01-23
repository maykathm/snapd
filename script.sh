#!/bin/bash

nums=$(gh pr list --repo github.com/canonical/snapd --search "merged:>=$(date -d 'today - 14 days' +%Y-%m-%d) -label:Skip spread" --json number --jq '.[].number')
prs=()
for num in $nums; do
    labels=$(gh pr view --repo github.com/canonical/snapd $num --json labels | jq -r '.labels[].name')
    if ! grep -q 'Skip spread' <<<"$labels" && ! grep -q 'Run only one system' <<<"$labels"; then
        prs+=("$num")
    fi
done
echo ""
echo "---------------------------------------------------------------------------------------------------------------"
echo "         Stats for PRs merged in the past 14 days without the 'Skip spread' label"
echo ""
printf "%-50s %15s %20s %15s\n" "PR URL" "# Run Attempts" "# Final Spread Failures" "Force merged?"
echo "---------------------------------------------------------------------------------------------------------------"
attempts=()
failures=()
forces=0
for pr in ${prs[@]}; do
    commit="$(gh pr view "$pr" --repo github.com/canonical/snapd --json headRefOid --jq .headRefOid)"
    attempt="$(gh run list --repo github.com/canonical/snapd --commit $commit --workflow 'ci-test.yaml' --json attempt --jq 'first(.[].attempt)')"
    num_failures="$(gh pr view "$pr" --json comments --jq '.comments[] | select(.author.login == "github-actions") | .body' | grep '^-' | wc -l)"
    attempts=$((attempts + $attempt))
    failures=$((failures + $num_failures))
    forced="no"
    if gh pr view "$pr" --json comments --jq '.comments[] | select(.author.login == "github-actions") | .body' | grep '^-' | grep -Ev '(-arm|debian-sid|ubuntu-26|garden|25.10|-fips)' | grep -Eq '(amazon|arch|debian|ubuntu)'; then
        forced="yes"
        forces=$((forces + 1))
    fi
    printf "%-50s %15d %20d %15s\n" "https://github.com/canonical/snapd/pull/$pr" "$attempt" "$num_failures" "$forced"
done
count=${#prs[@]}
avg_attempts="$(echo "scale=1; $attempts / $count" | bc)"
avg_failures="$(echo "scale=1; $failures / $count" | bc)"
percent_forced="$(echo "scale=1; ($forces / $count) * 100" | bc)"
echo "     ----------"
printf "%-50s %15.1f %20.1f %15.1f%%\n" "TOTAL AVERAGE" "$avg_attempts" "$avg_failures" "$percent_forced"
