#!/bin/bash
# Discard the containers created by incus-allocate.sh for the
# testing container reachable at the given "<ip>:22" address.
set -eu -o pipefail

address="${1:?usage: $0 <ip:port>}"
ip="${address%:*}"
ip="${ip#[}"
ip="${ip%]}"

if [[ "$ip" == *:* ]]; then
    testing=$(incus list --format csv -c n6 | grep -F ",$ip " | cut -d, -f1 || true)
else
    testing=$(incus list --format csv -c n4 | grep -F ",$ip " | cut -d, -f1 || true)
fi
if [[ "$testing" != spread-testing-* ]]; then
    echo "error: cannot find spread testing container with address $ip" >&2
    exit 1
fi

suffix="${testing#spread-testing-}"
incus delete -f "$testing"
incus delete -f "spread-fakestore-$suffix" || true
