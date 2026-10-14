#!/bin/bash
set -euo pipefail

: "${FAKESTORE_DATA:?FAKESTORE_DATA must be set}"

mkdir -p "$FAKESTORE_DATA/asserts"

pushd "$FAKESTORE_DATA"
for snap_name in hello-world core core24 test-snapd-tools; do
	snap download --basename="$snap_name" "$snap_name"
	mv "$snap_name.assert" asserts/
done
popd
