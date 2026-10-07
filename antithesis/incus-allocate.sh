#!/bin/bash
# Allocate a testing container and a fake store container on the project's
# default Incus network. Host artifacts are staged in the testing container under
# /var/tmp/spread-host for the spread project prepare to consume.
#
# Only the SSH address of the testing container is written to stdout.
#
# Environment:
#   TESTING_TARBALL_PATH     unified incus image tarball for the testing container
#   FAKE_STORE_TARBALL_PATH  unified incus image tarball for the fake store container
#   SPREAD_PASSWORD          password to set for the ubuntu user used by spread
set -eu -o pipefail

# Keep stdout clean for the address, everything else goes to stderr.
exec 3>&1 1>&2

: "${TESTING_TARBALL_PATH:?TESTING_TARBALL_PATH must be set}"
: "${FAKE_STORE_TARBALL_PATH:?FAKE_STORE_TARBALL_PATH must be set}"

SPREAD_PASSWORD="${SPREAD_PASSWORD:-ubuntu}"

for f in "$TESTING_TARBALL_PATH" "$FAKE_STORE_TARBALL_PATH"; do
    if [[ ! -f "$f" ]]; then
        echo "error: cannot find $f"
        exit 1
    fi
done

suffix=$(od -An -N3 -tx1 /dev/urandom | tr -d ' \n')
testing="spread-testing-$suffix"
fakestore="spread-fakestore-$suffix"

# The fingerprint of a unified image tarball is its sha256, so an image that
# was imported by a previous allocation can be reused.
import_image() {
    local tarball="$1"
    local fingerprint
    fingerprint=$(sha256sum "$tarball" | cut -d' ' -f1)
    if ! incus image info "$fingerprint" >/dev/null 2>&1; then
        incus image import "$tarball" >&2
    fi
    echo "$fingerprint"
}

wait_for_address() {
    local name="$1"
    local ip
    for _ in $(seq 10); do
        ip=$(incus list "^${name}\$" --format csv -c 4 | cut -d' ' -f1)
        if [[ -n "$ip" ]]; then
            printf '4 %s\n' "$ip"
            return 0
        fi
        sleep 1
    done

    for _ in $(seq 30); do
        ip=$(incus list "^${name}\$" --format csv -c 6 | cut -d, -f1)
        ip="${ip#6 }"
        ip="${ip%% *}"
        if [[ -n "$ip" ]]; then
            printf '6 %s\n' "$ip"
            return 0
        fi
        sleep 1
    done

    echo "error: $name did not get an IPv4 or IPv6 address" >&2
    return 1
}

# systemd may not have its bus up yet right after start.
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

cleanup_on_error() {
    incus delete -f "$testing" >/dev/null 2>&1 || true
    incus delete -f "$fakestore" >/dev/null 2>&1 || true
}
trap cleanup_on_error ERR

testing_image=$(import_image "$TESTING_TARBALL_PATH")
fakestore_image=$(import_image "$FAKE_STORE_TARBALL_PATH")

incus init "$fakestore_image" "$fakestore"
incus init "$testing_image" "$testing"
incus start "$fakestore"
incus start "$testing"

fakestore_address=$(wait_for_address "$fakestore")
read -r fakestore_family fakestore_ip <<< "$fakestore_address"
testing_address=$(wait_for_address "$testing")
read -r testing_family testing_ip <<< "$testing_address"

wait_for_boot "$testing"

incus exec "$testing" -- sh -c "echo '$fakestore_ip fakestore' >> /etc/hosts"

exec 1>&3 3>&-
if [[ "$testing_family" == 6 ]]; then
    echo "[$testing_ip]:22"
else
    echo "$testing_ip:22"
fi
