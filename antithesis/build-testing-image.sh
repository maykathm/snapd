#!/bin/bash
# Build the Antithesis testing container and export it as an Incus image.
#
# Usage: ./build-testing-image.sh <snapd-snap> [output-tarball]
#
# Environment:
#   BASE_IMAGE        incus image to build from (default: images:ubuntu/26.04)
#   FAKE_STORE_PORT   fakestore port (default: 11028)
#   SNAPD_DEBUG_HTTP  snapd HTTP debug level (default: 7)
set -eu -o pipefail

SNAPD_SNAP_PATH="${1:?Usage: $0 <snapd-snap> [output-tarball]}"
OUTPUT="${2:-$PWD/testing-image.tar.gz}"
BASE_IMAGE="${BASE_IMAGE:-images:ubuntu/26.04}"
FAKE_STORE_PORT="${FAKE_STORE_PORT:-11028}"
SNAPD_DEBUG_HTTP="${SNAPD_DEBUG_HTTP:-7}"

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

if [[ ! -f "$SNAPD_SNAP_PATH" ]]; then
    echo "error: cannot find snapd snap $SNAPD_SNAP_PATH" >&2
    exit 1
fi
if [[ "$OUTPUT" != *.tar.gz ]]; then
    echo "error: output must end with .tar.gz" >&2
    exit 1
fi

suffix=$(od -An -N3 -tx1 /dev/urandom | tr -d ' \n')
builder="testing-build-$suffix"
alias="testing-image-$suffix"

cleanup() {
    incus delete -f "$builder" >/dev/null 2>&1 || true
    incus image delete "$alias" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_for_boot() {
    local state
    for _ in $(seq 120); do
        state=$(incus exec "$builder" -- systemctl is-system-running 2>/dev/null || true)
        case "$state" in
            running|degraded)
                return 0
                ;;
        esac
        sleep 1
    done
    echo "error: $builder did not finish booting" >&2
    return 1
}

wait_for_network() {
    for _ in $(seq 60); do
        if incus exec "$builder" -- getent hosts archive.ubuntu.com >/dev/null; then
            return 0
        fi
        sleep 1
    done
    echo "error: $builder has no network access" >&2
    return 1
}

echo "Building testing image in $builder"
incus launch "$BASE_IMAGE" "$builder"
wait_for_boot
wait_for_network
incus exec "$builder" -- env DEBIAN_FRONTEND=noninteractive sh -ec \
    'apt update && apt upgrade -y && apt install -y snapd sudo apparmor squashfs-tools liblzo2-2 gnupg ssh wget'
incus exec "$builder" -- sh -ec '
    if ! id test >/dev/null 2>&1; then
        groupadd --gid 12345 test
        useradd --create-home --uid 12345 --gid 12345 --shell /bin/bash test
    fi
    echo "test:test" | chpasswd
    usermod -aG sudo test
    if getent group systemd-journal >/dev/null; then
        usermod -aG systemd-journal test
    fi
    printf "%s\n" "test ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/90-spread-test
    chmod 0440 /etc/sudoers.d/90-spread-test
    visudo -cf /etc/sudoers.d/90-spread-test
    mkdir -p /etc/ssh/sshd_config.d
    echo "PasswordAuthentication yes" > /etc/ssh/sshd_config.d/spread.conf
'
incus exec "$builder" -- mkdir -p /opt/snapd-test-support
tar -C "$script_dir/../tests" -cf - lib bin | incus exec "$builder" -- \
    tar --no-same-owner -C /opt/snapd-test-support -xf -
incus exec "$builder" -- sh -ec '
    support_dir=/opt/snapd-test-support
    cp -f "$support_dir"/lib/external/snapd-testing-tools/tools/* "$support_dir/lib/tools/"
    wget -O /tmp/gojq.tar.gz https://github.com/itchyny/gojq/releases/download/v0.12.16/gojq_v0.12.16_linux_amd64.tar.gz
    tar -xf /tmp/gojq.tar.gz -C "$support_dir/bin" --strip-components=1 --wildcards "*/gojq"
    test -x "$support_dir/bin/gojq"
    rm -f /tmp/gojq.tar.gz
'
incus file push --uid 12346 --gid 12346 "$SNAPD_SNAP_PATH" "$builder/tmp/snapd.snap"
incus exec "$builder" -- snap install --dangerous /tmp/snapd.snap
incus exec "$builder" -- sh -ec '
    mkdir -p /etc/systemd/system/snapd.service.d
    cat > /etc/systemd/system/snapd.service.d/fakestore.conf <<EOF
[Service]
Environment=SNAPD_DEBUG=1
Environment=SNAPPY_TESTING=1
Environment=SNAPD_DEBUG_HTTP=$2
Environment=SNAPPY_FORCE_API_URL=http://fakestore:$1
EOF
    systemctl daemon-reload
    systemctl restart snapd.service
' sh "$FAKE_STORE_PORT" "$SNAPD_DEBUG_HTTP"
incus exec "$builder" -- rm -f /tmp/snapd.snap

incus stop "$builder"
incus publish "$builder" --alias "$alias" --compression gzip
incus image export "$alias" "${OUTPUT%.tar.gz}"

echo "Testing image written to $OUTPUT"