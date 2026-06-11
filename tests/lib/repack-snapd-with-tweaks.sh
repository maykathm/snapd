#!/bin/bash

set -euo pipefail
set -x

usage() {
    cat <<'EOF'
usage: repack-snapd-with-tweaks.sh --input-snap PATH [options]

Repack a snapd snap with spread first-boot tweak units/scripts (run mode and install mode)
so local Ubuntu Core images behave like setup_reflash_magic tests.

Required:
  --input-snap PATH           Input snapd snap to repack

Options:
  --output-snap PATH          Output snap path (default: <input-dir>/snapd_with_tweaks.snap)
  --generate-coverage         Sets up GOCOVERDIR for snapd
  --gocoverdir PATH           Coverage directory for run-mode overrides (default: /var/tmp/snapd-tools/coverage)
  -h, --help                  Show this help

Examples:
  tests/lib/tools/repack-snapd-with-tweaks.sh --input-snap ./snapd_1337.snap
  tests/lib/tools/repack-snapd-with-tweaks.sh --input-snap ./snapd_1337.snap --core-version 26 --force-install-tweaks
EOF
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "missing required command: $1" >&2
        exit 1
    }
}

abspath() {
    readlink -f "$1"
}

add_install_mode_tweaks() {
    local unpack_dir="$1"

    if [ "$GENERATE_COVERAGE" = "false" ]; then
        return
    fi

    local install_coverdir
    install_coverdir=/run/mnt/ubuntu-seed/go-cover

    cat > "$unpack_dir"/lib/systemd/system/snapd.spread-tests-install-mode-tweaks.service <<'EOF'
[Unit]
Description=Tweaks to install mode for spread tests
Before=snapd.service
Documentation=man:snap(1)

[Service]
Type=oneshot
ExecStart=/usr/lib/snapd/snapd.spread-tests-install-mode-tweaks.sh
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
EOF

    cat > "$unpack_dir"/usr/lib/snapd/snapd.spread-tests-install-mode-tweaks.sh <<EOF
#!/bin/sh
set -ex
if ! [ -e /root/first-install-mode-touch ]; then
    touch /root/first-install-mode-touch
fi
# We look at modeenv as that is authoritative if installing from the initramfs.
if [ -f /var/lib/snapd/modeenv ]; then
    if ! grep -E '^mode=install$' /var/lib/snapd/modeenv; then
        echo "not in install mode - script not running"
        exit 0
    fi
elif ! grep -E 'snapd_recovery_mode=install' /proc/cmdline; then
    echo "not in install mode - script not running"
    exit 0
fi
if [ -e /root/spread-install-setup-done ]; then
    exit 0
fi

mkdir -p "$install_coverdir"
if [ -z "$install_coverdir" ]; then
    echo "cannot locate persistent mount for install-mode coverage"
    exit 1
fi
echo "spread coverage: install-mode persistent source=$install_coverdir"
chmod 777 "$install_coverdir"
echo "spread coverage: install-mode using persistent GOCOVERDIR=$install_coverdir"

mkdir -p "/run/mnt/data/system-data/etc/systemd/system/snapd.service.d"
cat <<EOF2 >/run/mnt/data/system-data/etc/systemd/system/snapd.service.d/43-generate-coverage.conf
[Service]
Environment=GOCOVERDIR=$install_coverdir
EOF2

touch /root/spread-install-setup-done
EOF

    chmod 0755 "$unpack_dir"/usr/lib/snapd/snapd.spread-tests-install-mode-tweaks.sh
}

add_run_mode_tweaks() {
    local unpack_dir="$1"

    cat > "$unpack_dir"/lib/systemd/system/snapd.spread-tests-run-mode-tweaks.service <<'EOF'
[Unit]
Description=Tweaks to run mode for spread tests
Before=snapd.service
Documentation=man:snap(1)

[Service]
Type=oneshot
ExecStart=/usr/lib/snapd/snapd.spread-tests-run-mode-tweaks.sh
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
EOF

    cat > "$unpack_dir"/usr/lib/snapd/snapd.spread-tests-run-mode-tweaks.sh <<'EOF'
#!/bin/sh
set -ex
# ensure we don't enable ssh in install mode or spread will get confused
# We look at modeenv as that is authoritative if installing from the initramfs.
if [ -f /var/lib/snapd/modeenv ]; then
    if ! grep -E '^mode=(run|recover)$' /var/lib/snapd/modeenv; then
        echo "not in run or recovery mode - script not running"
        exit 0
    fi
elif ! grep -E 'snapd_recovery_mode=(run|recover)' /proc/cmdline; then
    echo "not in run or recovery mode - script not running"
    exit 0
fi
if [ -e /root/spread-setup-done ]; then
    exit 0
fi

# extract data from previous stage
(cd / && tar xf /run/mnt/ubuntu-seed/run-mode-overlay-data.tar.gz)

# user db - it's complicated
for f in group gshadow passwd shadow; do
    cat >/etc/systemd/system/etc-"$f".mount <<EOF2
[Unit]
Description=Mount root/test-etc/$f over system etc/$f
Before=ssh.service

[Mount]
What=/root/test-etc/$f
Where=/etc/$f
Type=none
Options=bind,ro

[Install]
WantedBy=multi-user.target
EOF2
    systemctl enable etc-"$f".mount
    systemctl start etc-"$f".mount
done

mkdir -p /home/test
chown 12345:12345 /home/test
mkdir -p /home/ubuntu
chown 1000:1000 /home/ubuntu
mkdir -p /etc/sudoers.d/
echo 'test ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers.d/99-test-user
echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers.d/99-ubuntu-user
sed -i 's/\#\?\(PermitRootLogin\|PasswordAuthentication\)\>.*/\1 yes/' /etc/ssh/sshd_config
echo "MaxAuthTries 120" >> /etc/ssh/sshd_config
grep '^PermitRootLogin yes' /etc/ssh/sshd_config
if systemctl is-active ssh; then
   systemctl reload ssh
fi

touch /root/spread-setup-done
EOF

    if [ "$GENERATE_COVERAGE" = "true" ]; then
        local conf_file
        conf_file=99-generate-coverage.conf

        cat >> "$unpack_dir"/usr/lib/snapd/snapd.spread-tests-run-mode-tweaks.sh <<EOF
mkdir -p "$GOCOVERDIR"
EOF

        while IFS= read -r line; do
            dir=$(sed -E 's|^(.*)\.in$|/etc/systemd/system/\1.d|' <<<"$line")
            cat >> "$unpack_dir"/usr/lib/snapd/snapd.spread-tests-run-mode-tweaks.sh <<EOF
mkdir -p "$dir"
cat <<EOF2 >"$dir/$conf_file"
[Service]
Environment=GOCOVERDIR=$GOCOVERDIR
EOF2
EOF
        done < <(find "$SNAPD_DIR"/data/systemd "$SNAPD_DIR"/data/systemd-user -type f -name '*.service.in' -exec basename {} \;)
    fi

    chmod 0755 "$unpack_dir"/usr/lib/snapd/snapd.spread-tests-run-mode-tweaks.sh
}

INPUT_SNAP=
OUTPUT_SNAP=
GENERATE_COVERAGE=false
GOCOVERDIR=/var/tmp/snapd-tools/coverage
FORCE_INSTALL_TWEAKS=false

while [ $# -gt 0 ]; do
    case "$1" in
        --input-snap)
            INPUT_SNAP="${2:-}"
            shift 2
            ;;
        --output-snap)
            OUTPUT_SNAP="${2:-}"
            shift 2
            ;;
        --generate-coverage)
            GENERATE_COVERAGE="true"
            shift 1
            ;;
        --gocoverdir)
            GOCOVERDIR="${2:-}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [ -z "$INPUT_SNAP" ]; then
    echo "--input-snap is required" >&2
    usage >&2
    exit 1
fi

case "$GENERATE_COVERAGE" in
    true|false)
        ;;
    *)
        echo "--generate-coverage must be true or false" >&2
        exit 1
        ;;
esac

require_cmd unsquashfs
require_cmd snap
require_cmd find
require_cmd sed

INPUT_SNAP="$(abspath "$INPUT_SNAP")"
if [ ! -f "$INPUT_SNAP" ]; then
    echo "input snap not found: $INPUT_SNAP" >&2
    exit 1
fi

if [ -z "$OUTPUT_SNAP" ]; then
    OUTPUT_SNAP="$(dirname "$INPUT_SNAP")/snapd_with_tweaks.snap"
fi
OUTPUT_SNAP="$(abspath "$OUTPUT_SNAP")"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SNAPD_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

TMP_DIR="$(mktemp -d /tmp/snapd-repack.XXXXXXXX)"
cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "Unpacking $INPUT_SNAP"
unsquashfs -no-progress -f -d "$TMP_DIR/unpack" "$INPUT_SNAP"

echo "Adding run-mode tweaks"
add_run_mode_tweaks "$TMP_DIR/unpack"

echo "Adding install-mode tweaks"
add_install_mode_tweaks "$TMP_DIR/unpack"

echo "Packing tweaked snap to $OUTPUT_SNAP"
snap pack --filename="$OUTPUT_SNAP" "$TMP_DIR/unpack"

echo "Done: $OUTPUT_SNAP"
