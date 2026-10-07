#!/bin/bash
# Build the fakestore in an incus container and package it as an incus image
# tarball that can be used as FAKE_STORE_TARBALL_PATH.
#
# The resulting image runs fakestore as a systemd service listening on
# all IPv4 and IPv6 addresses at $FAKE_STORE_PORT and serving snaps from
# /var/lib/fakestore.
#
# Usage: ./build-fakestore-image.sh [output-tarball]
#
# Environment:
#   BASE_IMAGE       incus image to build and run the fakestore on (default: images:ubuntu/26.04)
#   FAKE_STORE_PORT  port for the fakestore to listen on (default: 11028)
#   FAKESTORE_DATA   optional directory with snaps and asserts/ to bake into the image
set -eu -o pipefail

OUTPUT="${1:-$PWD/fakestore-image.tar.gz}"
BASE_IMAGE="${BASE_IMAGE:-images:ubuntu/26.04}"
FAKE_STORE_PORT="${FAKE_STORE_PORT:-11028}"
FAKESTORE_DATA="${FAKESTORE_DATA:-}"

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd "$script_dir/.." && pwd)

# incus image export appends the extension itself.
if [[ "$OUTPUT" != *.tar.gz ]]; then
    echo "error: output must end with .tar.gz" >&2
    exit 1
fi

if [[ -n "$FAKESTORE_DATA" && ! -d "$FAKESTORE_DATA" ]]; then
    echo "error: cannot find directory $FAKESTORE_DATA" >&2
    exit 1
fi

suffix=$(od -An -N3 -tx1 /dev/urandom | tr -d ' \n')
builder="fakestore-build-$suffix"
runner="fakestore-image-$suffix"
alias="fakestore-image-$suffix"

tmpdir=$(mktemp -d)
cleanup() {
    rm -rf "$tmpdir"
    incus delete -f "$builder" >/dev/null 2>&1 || true
    incus delete -f "$runner" >/dev/null 2>&1 || true
    incus image delete "$alias" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# systemd may not have its bus up yet right after launch.
wait_for_boot() {
    local name="$1"
    local state
    for _ in $(seq 120); do
        state=$(incus exec "$name" -- systemctl is-system-running 2>/dev/null || true)
        case "$state" in
            running|degraded)
                return 0
                ;;
        esac
        sleep 1
    done
    echo "error: $name did not finish booting" >&2
    return 1
}

wait_for_network() {
    local name="$1"
    for _ in $(seq 60); do
        if incus exec "$name" -- getent hosts archive.ubuntu.com >/dev/null; then
            return 0
        fi
        sleep 1
    done
    echo "error: $name has no network access" >&2
    return 1
}

echo "Building fakestore in $builder"
incus launch "$BASE_IMAGE" "$builder"
wait_for_boot "$builder"
wait_for_network "$builder"
incus exec "$builder" -- sh -ec '
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt update && apt upgrade -y && apt install -y golang-go
'

# Ship tracked and untracked-but-not-ignored files, including local changes.
incus exec "$builder" -- mkdir -p /src
(
    cd "$repo_dir"
    git ls-files -z --cached --others --exclude-standard \
        | tar --null --ignore-failed-read -T - -cf -
) | incus exec "$builder" -- tar --no-same-owner -C /src -xf -

incus exec "$builder" --cwd /src --env CGO_ENABLED=0 -- \
    go build -o /tmp/fakestore ./tests/lib/fakestore/cmd/fakestore
incus file pull "$builder/tmp/fakestore" "$tmpdir/fakestore"
incus delete -f "$builder"

echo "Packaging fakestore in $runner"
incus launch "$BASE_IMAGE" "$runner"
wait_for_boot "$runner"
wait_for_network "$runner"
incus exec "$runner" -- sh -ec '
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt install -y squashfs-tools
'

incus file push --mode 0755 "$tmpdir/fakestore" "$runner/usr/local/bin/fakestore"
incus exec "$runner" -- mkdir -p /var/lib/fakestore/asserts
if [[ -n "$FAKESTORE_DATA" ]]; then
    tar -C "$FAKESTORE_DATA" -cf - . | incus exec "$runner" -- tar --no-same-owner -C /var/lib/fakestore -xf -
fi

cat > "$tmpdir/fakestore.service" <<EOF
[Unit]
Description=snapd fake store
After=network-online.target
Wants=network-online.target

[Service]
Environment=SNAPPY_TESTING=1
Environment=SNAPD_DEBUG=1
Environment=SNAPD_DEBUG_HTTP=7
Environment=GODEBUG=rsa1024min=0
ExecStart=/usr/local/bin/fakestore run --dir /var/lib/fakestore --addr [::]:$FAKE_STORE_PORT
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
incus file push "$tmpdir/fakestore.service" "$runner/etc/systemd/system/fakestore.service"
incus exec "$runner" -- systemctl enable fakestore.service

incus stop "$runner"
incus publish "$runner" --alias "$alias" --compression gzip
incus image export "$alias" "${OUTPUT%.tar.gz}"

echo "Fakestore image written to $OUTPUT"
