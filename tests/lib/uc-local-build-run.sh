#!/bin/bash

set -euo pipefail

usage() {
    cat <<'EOF'
usage: uc-local-build-run.sh --snapd-snap PATH [options]

Build an Ubuntu Core image with ubuntu-image, inject root login config,
and launch it in QEMU for local iteration.

Required:
  --snapd-snap PATH         Path to snapd snap to seed in image

Options:
  --core-version N          Core track/version (20, 22, 24, 26). Default: 24
  --arch ARCH               Architecture for model selection (amd64, arm64). Default: amd64
  --model PATH              Model assertion path. Default: tests/lib/assertions/ubuntu-core-<version>-<arch>.model
  --kernel-snap PATH        Use local pc-kernel snap instead of downloading
  --base-snap PATH          Use local core<version> base snap instead of downloading
  --kernel-channel NAME     Kernel channel risk. Default: stable
  --gadget-channel NAME     Gadget channel risk. Default: stable
  --base-channel NAME       Base channel risk. Default: stable
  --output-dir DIR          Output directory. Default: /tmp/uc-local-image
  --image-size SIZE         ubuntu-image --image-size value. Default: 5G
  --qemu-mem MB             QEMU memory in MB. Default: 4096
  --qemu-cpus N             QEMU CPU count. Default: 2
  --ssh-port PORT           Host port forwarded to guest 22. Default: 8022
  --monitor-port PORT       QEMU monitor TCP port. Default: 8888
  --serial-mode MODE        Serial mode: file or socket. Default: file
  --serial-port PORT        Serial telnet port in socket mode. Default: 7777
  --no-run                  Build image but do not launch QEMU
  -h, --help                Show this help

Examples:
    tests/lib/tools/uc-local-build-run.sh --snapd-snap ./snapd_1337.snap
    tests/lib/tools/uc-local-build-run.sh --snapd-snap ./snapd_1337.snap --core-version 26 --base-snap ./core26_local.snap
    tests/lib/tools/uc-local-build-run.sh --snapd-snap ./snapd_1337.snap --serial-mode socket
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

find_one_file() {
    local dir="$1"
    local pattern="$2"
    local file

    file="$(find "$dir" -maxdepth 1 -type f -name "$pattern" | head -n1 || true)"
    if [ -z "$file" ]; then
        return 1
    fi
    echo "$file"
}

download_snap() {
    local name="$1"
    local channel="$2"
    local dir="$3"

    snap download --basename="$name" --channel="$channel" "$name"
    mv -f "$name".snap "$dir"/
    if [ -f "$name".assert ]; then
        mv -f "$name".assert "$dir"/
    fi
}

inject_root_cloud_init() {
    local image="$1"
    local arch="$2"
    local work_dir="$3"

    local devloop seed_dev tmp cfg

    cfg="$work_dir/99-root-login.cfg"
    cat > "$cfg" <<'EOF'
#cloud-config
ssh_pwauth: true
disable_root: false
chpasswd:
  expire: false
  users:
    - {name: root, password: root, type: text}
EOF

    devloop="$(losetup -f --show -P "$image")"
    seed_dev="${devloop}p2"
    if [ "$arch" = "arm64" ]; then
        # On arm images, ubuntu-seed is commonly p1.
        seed_dev="${devloop}p1"
    fi

    if [ ! -b "$seed_dev" ]; then
        partx -u "$devloop"
    fi
    if [ ! -b "$seed_dev" ]; then
        echo "cannot find ubuntu-seed partition device: $seed_dev" >&2
        losetup -d "$devloop"
        exit 1
    fi

    tmp="$(mktemp -d)"
    mount "$seed_dev" "$tmp"
    mkdir -p "$tmp/data/etc/cloud/cloud.cfg.d"
    cp -f "$cfg" "$tmp/data/etc/cloud/cloud.cfg.d/"
    sync
    umount "$tmp"
    rmdir "$tmp"
    losetup -d "$devloop"
}

CORE_VERSION=24
ARCH=amd64
MODEL=
SNAPD_SNAP=
KERNEL_SNAP=
BASE_SNAP=
KERNEL_CHANNEL=stable
GADGET_CHANNEL=stable
BASE_CHANNEL=stable
OUTPUT_DIR=/tmp/uc-local-image
IMAGE_SIZE=5G
QEMU_MEM=4096
QEMU_CPUS=2
SSH_PORT=8022
MONITOR_PORT=8888
SERIAL_MODE=file
SERIAL_PORT=7777
RUN_QEMU=true

while [ $# -gt 0 ]; do
    case "$1" in
        --snapd-snap)
            SNAPD_SNAP="${2:-}"
            shift 2
            ;;
        --core-version)
            CORE_VERSION="${2:-}"
            shift 2
            ;;
        --arch)
            ARCH="${2:-}"
            shift 2
            ;;
        --model)
            MODEL="${2:-}"
            shift 2
            ;;
        --kernel-snap)
            KERNEL_SNAP="${2:-}"
            shift 2
            ;;
        --base-snap)
            BASE_SNAP="${2:-}"
            shift 2
            ;;
        --kernel-channel)
            KERNEL_CHANNEL="${2:-}"
            shift 2
            ;;
        --gadget-channel)
            GADGET_CHANNEL="${2:-}"
            shift 2
            ;;
        --base-channel)
            BASE_CHANNEL="${2:-}"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="${2:-}"
            shift 2
            ;;
        --image-size)
            IMAGE_SIZE="${2:-}"
            shift 2
            ;;
        --qemu-mem)
            QEMU_MEM="${2:-}"
            shift 2
            ;;
        --qemu-cpus)
            QEMU_CPUS="${2:-}"
            shift 2
            ;;
        --ssh-port)
            SSH_PORT="${2:-}"
            shift 2
            ;;
        --monitor-port)
            MONITOR_PORT="${2:-}"
            shift 2
            ;;
        --serial-mode)
            SERIAL_MODE="${2:-}"
            shift 2
            ;;
        --serial-port)
            SERIAL_PORT="${2:-}"
            shift 2
            ;;
        --no-run)
            RUN_QEMU=false
            shift
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

if [ -z "$SNAPD_SNAP" ]; then
    echo "--snapd-snap is required" >&2
    usage >&2
    exit 1
fi

case "$CORE_VERSION" in
    20|22|24|26)
        ;;
    *)
        echo "unsupported --core-version: $CORE_VERSION" >&2
        exit 1
        ;;
esac

case "$ARCH" in
    amd64|arm64)
        ;;
    *)
        echo "unsupported --arch: $ARCH" >&2
        exit 1
        ;;
esac

case "$SERIAL_MODE" in
    file|socket)
        ;;
    *)
        echo "unsupported --serial-mode: $SERIAL_MODE (use file or socket)" >&2
        exit 1
        ;;
esac

require_cmd snap
require_cmd losetup
require_cmd mount
require_cmd umount
require_cmd partx

if [ "$ARCH" = "amd64" ]; then
    require_cmd qemu-system-x86_64
    QEMU_BIN=qemu-system-x86_64
else
    require_cmd qemu-system-aarch64
    QEMU_BIN=qemu-system-aarch64
fi

SNAPD_SNAP="$(abspath "$SNAPD_SNAP")"
if [ ! -f "$SNAPD_SNAP" ]; then
    echo "snapd snap does not exist: $SNAPD_SNAP" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(abspath "$OUTPUT_DIR")"
WORK_DIR="$OUTPUT_DIR/work"
SNAPS_DIR="$WORK_DIR/snaps"
mkdir -p "$WORK_DIR" "$SNAPS_DIR"

if [ -z "$MODEL" ]; then
    MODEL="tests/lib/assertions/ubuntu-core-${CORE_VERSION}-${ARCH}.model"
fi
MODEL="$(abspath "$MODEL")"
if [ ! -f "$MODEL" ]; then
    echo "model file does not exist: $MODEL" >&2
    exit 1
fi

UBUNTU_IMAGE_BIN="${GOHOME:-$HOME/go}/bin/ubuntu-image"
if [ ! -x "$UBUNTU_IMAGE_BIN" ]; then
    if command -v ubuntu-image >/dev/null 2>&1; then
        UBUNTU_IMAGE_BIN="$(command -v ubuntu-image)"
    elif [ -x /snap/bin/ubuntu-image ]; then
        UBUNTU_IMAGE_BIN=/snap/bin/ubuntu-image
    else
        echo "ubuntu-image not found; install it first" >&2
        exit 1
    fi
fi

cp -f "$SNAPD_SNAP" "$SNAPS_DIR/"
SNAPD_FOR_IMAGE="$SNAPS_DIR/$(basename "$SNAPD_SNAP")"

if [ -n "$KERNEL_SNAP" ]; then
    KERNEL_SNAP="$(abspath "$KERNEL_SNAP")"
    cp -f "$KERNEL_SNAP" "$SNAPS_DIR/"
    KERNEL_FOR_IMAGE="$SNAPS_DIR/$(basename "$KERNEL_SNAP")"
else
    download_snap pc-kernel "${CORE_VERSION}/${KERNEL_CHANNEL}" "$SNAPS_DIR"
    KERNEL_FOR_IMAGE="$(find_one_file "$SNAPS_DIR" 'pc-kernel*.snap')"
fi

if [ -n "$BASE_SNAP" ]; then
    BASE_SNAP="$(abspath "$BASE_SNAP")"
    cp -f "$BASE_SNAP" "$SNAPS_DIR/"
    BASE_FOR_IMAGE="$SNAPS_DIR/$(basename "$BASE_SNAP")"
else
    download_snap "core${CORE_VERSION}" "$BASE_CHANNEL" "$SNAPS_DIR"
    BASE_FOR_IMAGE="$(find_one_file "$SNAPS_DIR" "core${CORE_VERSION}*.snap")"
fi

# Gadget follows setup_reflash_magic behavior and is always fetched from channel.
download_snap pc "${CORE_VERSION}/${GADGET_CHANNEL}" "$SNAPS_DIR"
GADGET_FOR_IMAGE="$(find_one_file "$SNAPS_DIR" 'pc*.snap' | grep -v 'pc-kernel' | head -n1)"

if [ -z "$GADGET_FOR_IMAGE" ]; then
    echo "cannot determine gadget snap path" >&2
    exit 1
fi

echo "Using assets:"
echo "  model:  $MODEL"
echo "  snapd:  $SNAPD_FOR_IMAGE"
echo "  kernel: $KERNEL_FOR_IMAGE"
echo "  gadget: $GADGET_FOR_IMAGE"
echo "  base:   $BASE_FOR_IMAGE"

# ubuntu-image uses host snap by default; force host /usr/bin/snap for compatibility.
UBUNTU_IMAGE_SNAP_CMD=/usr/bin/snap
export UBUNTU_IMAGE_SNAP_CMD

# Clean previous image outputs.
rm -f "$OUTPUT_DIR"/*.img

"$UBUNTU_IMAGE_BIN" snap \
    --image-size "$IMAGE_SIZE" \
    -w "$OUTPUT_DIR" "$MODEL" \
    --channel "${CORE_VERSION}/${GADGET_CHANNEL}" \
    --snap "$KERNEL_FOR_IMAGE" \
    --snap "$GADGET_FOR_IMAGE" \
    --snap "$BASE_FOR_IMAGE" \
    --snap "$SNAPD_FOR_IMAGE" \
    --output-dir "$OUTPUT_DIR"

IMAGE_PATH="$(find "$OUTPUT_DIR" -maxdepth 1 -name '*.img' | head -n1 || true)"
if [ -z "$IMAGE_PATH" ]; then
    echo "ubuntu-image did not produce an image in $OUTPUT_DIR" >&2
    exit 1
fi
IMAGE_PATH="$(abspath "$IMAGE_PATH")"

echo "Injecting root login cloud-init config into ubuntu-seed"
inject_root_cloud_init "$IMAGE_PATH" "$ARCH" "$WORK_DIR"

echo "Image ready: $IMAGE_PATH"
echo "SSH forward: localhost:${SSH_PORT} -> guest:22"
echo "root password: root"

if [ "$RUN_QEMU" = false ]; then
    exit 0
fi

SERIAL_LOG="$OUTPUT_DIR/serial.log"
: > "$SERIAL_LOG"

if [ "$SERIAL_MODE" = "file" ]; then
    SERIAL_ARGS=(-serial "file:${SERIAL_LOG}")
else
    SERIAL_ARGS=(
        -chardev "socket,telnet=on,host=localhost,server=on,port=${SERIAL_PORT},wait=off,id=char0,logfile=${SERIAL_LOG},logappend=on"
        -serial chardev:char0
    )
fi

echo "Launching QEMU (serial log at $SERIAL_LOG)"
if [ "$SERIAL_MODE" = "socket" ]; then
    echo "Serial telnet: telnet localhost ${SERIAL_PORT}"
fi
echo "QEMU monitor: tcp:127.0.0.1:${MONITOR_PORT}"

if [ "$ARCH" = "amd64" ]; then
    exec "$QEMU_BIN" \
        -enable-kvm \
        -m "$QEMU_MEM" \
        -smp "$QEMU_CPUS" \
        -nographic \
        -monitor tcp:127.0.0.1:"$MONITOR_PORT",server=on,wait=off \
        "${SERIAL_ARGS[@]}" \
        -drive file="$IMAGE_PATH",if=virtio,format=raw \
        -net nic,model=virtio \
        -net user,hostfwd=tcp::"$SSH_PORT"-:22
else
    exec "$QEMU_BIN" \
        -machine virt,highmem=off \
        -cpu cortex-a72 \
        -m "$QEMU_MEM" \
        -smp "$QEMU_CPUS" \
        -nographic \
        -monitor tcp:127.0.0.1:"$MONITOR_PORT",server=on,wait=off \
        "${SERIAL_ARGS[@]}" \
        -drive file="$IMAGE_PATH",if=virtio,format=raw \
        -netdev user,id=net0,hostfwd=tcp::"$SSH_PORT"-:22 \
        -device virtio-net-pci,netdev=net0
fi
