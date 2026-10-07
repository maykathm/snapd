#!/bin/sh

FAKE_STORE_TARBALL_PATH=$(find . -name fakestore-image.tar.gz)
if [ -z "$FAKE_STORE_TARBALL_PATH" ]; then
    echo "fake store tarball not found" >&2
    exit 1
fi
export FAKE_STORE_TARBALL_PATH

TESTING_TARBALL_PATH=$(find . -name testing-image.tar.gz)
if [ -z "$TESTING_TARBALL_PATH" ]; then
    echo "testing tarball not found" >&2
    exit 1
fi
export TESTING_TARBALL_PATH

spread_yaml=$(find . -name spread.yaml)
if [ -z "$spread_yaml" ]; then
    echo "spread.yaml not found" >&2
    exit 1
fi
spread_dir=$(cd "$(dirname "$spread_yaml")" && pwd)
if ! [ -f "$spread_dir"/spread-plus ]; then
    echo "spread-plus not found" >&2
    exit 1
fi
if ! [ -d "$spread_dir"/tests ]; then
    echo "spread tests not found" >&2
    exit 1
fi
if ! [ -f "$spread_dir"/incus-allocate.sh ]; then
    echo "incus-allocate.sh not found" >&2
    exit 1
fi
if ! [ -f "$spread_dir"/incus-discard.sh ]; then
    echo "incus-discard.sh not found" >&2
    exit 1
fi

(
    cd "$spread_dir"
    ./spread-plus adhoc:ubuntu-26.04-64:tests/...
)
