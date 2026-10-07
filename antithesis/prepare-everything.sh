#!/bin/bash
set -euo pipefail

: "${PREP_DIR:?PREP_DIR must be set}"

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

if ! [ -d "$script_dir/../built-snap" ]; then
	(
		cd "$script_dir"/../
		tests/build-test-snapd-snap
	)
fi

SNAPD_SNAP_PATH=$(find "$script_dir"/../built-snap -name "*.snap.keep")
if [ -z "$SNAPD_SNAP_PATH" ]; then
	echo "Something went wrong with detecting snapd snap" >&2
	exit 1
fi

mkdir -p "$PREP_DIR"

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

pushd "$PREP_DIR"

FAKESTORE_DATA="$tmpdir" bash "$script_dir/download-snaps.sh"
FAKESTORE_DATA="$tmpdir" bash "$script_dir/build-fakestore-image.sh" "$PREP_DIR/fakestore-image.tar.gz"
cat > "$PREP_DIR"/fakestore.dockerfile << EOF
FROM scratch
COPY fakestore-image.tar.gz /fakestore-image.tar.gz
EOF
docker build -t snapd-fakestore -f fakestore.dockerfile .

bash "$script_dir/build-testing-image.sh" "$SNAPD_SNAP_PATH" "$PREP_DIR/testing-image.tar.gz"
cat > "$PREP_DIR"/testing-image.dockerfile << EOF
FROM scratch
COPY testing-image.tar.gz /testing-image.tar.gz
EOF
docker build -t snapd-testing-image -f "$PREP_DIR"/testing-image.dockerfile .

wget https://github.com/canonical/spread-plus/releases/download/2026.09.22/spread-plus-amd64.tar.gz
tar -xf spread-plus-amd64.tar.gz -C "$PREP_DIR"

cp "$script_dir"/spread.yaml "$PREP_DIR"
cp -r "$script_dir"/tests "$PREP_DIR"
cp "$script_dir"/incus-allocate.sh "$PREP_DIR"
cp "$script_dir"/incus-discard.sh "$PREP_DIR"
cp "$script_dir"/run.sh "$PREP_DIR"

cat > "$PREP_DIR"/run-on-host.dockerfile << EOF
FROM scratch
COPY spread-plus /spread-plus
COPY spread.yaml /spread.yaml
COPY tests /tests
COPY incus-allocate.sh /incus-allocate.sh
COPY incus-discard.sh /incus-discard.sh
COPY run.sh /run.sh
EOF

docker build -t snapd-run-on-host -f "$PREP_DIR"/run-on-host.dockerfile .

popd
