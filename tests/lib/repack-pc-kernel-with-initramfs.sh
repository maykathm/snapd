#!/bin/bash

set -euo pipefail

usage() {
    cat <<'EOF'
usage: repack-pc-kernel-with-initramfs.sh --input-kernel-snap PATH [options]

Repack a pc-kernel snap by rebuilding its initramfs and injecting a snap-bootstrap wrapper,
mirroring setup_reflash_magic logic used in tests/lib/prepare.sh.

Options:
  --input-kernel-snap PATH      Input pc-kernel snap (if not specified, defaults to pc-kernel snap in stable channel)
  --output-dir DIR              Output directory for resulting snap (default: current directory)
  --core-version N              Core version path to use (20, 22, 24, 26). Default: 24
    --kernel-channel NAME         Kernel risk channel on the UC track. Default: stable
  --arch ARCH                   Arch hint (amd64, arm64, armhf). Default: amd64
    --snapd-snap PATH             Repacked snapd snap used to source snap-bootstrap
    --use-lxd-container           Run all build/repack steps in a temporary LXD container
    --lxd-image IMAGE             LXD image for container mode. Default: ubuntu:24.04
  --inject-kernel-panic         Append forced panic line to wrapper
    --generate-coverage           Enables bootstrap GOCOVERDIR setup
  --extra-initrd DIR            Directory copied into unpacked initrd
  --extra-kernel-snap DIR       Directory copied into kernel snap root before packing
  --epoch-bump-time TS          Unix timestamp for clock-epoch touch (UC20/22 path only)
  -h, --help                    Show help

Examples:
    tests/lib/repack-pc-kernel-with-initramfs.sh --input-kernel-snap ./pc-kernel.snap --core-version 24
    tests/lib/repack-pc-kernel-with-initramfs.sh --input-kernel-snap ./pc-kernel.snap --snapd-snap ./snapd_tweaked.snap --core-version 20 --inject-kernel-panic
    tests/lib/repack-pc-kernel-with-initramfs.sh --use-lxd-container --core-version 24 --kernel-channel edge
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

# Global flag so cleanup_lxd can reference it without hitting set -u.
_LXD_CT_NAME=
_LXD_CREATED=false

cleanup_lxd() {
    if [ "$_LXD_CREATED" = "true" ]; then
        lxc delete --force "$_LXD_CT_NAME" >/dev/null 2>&1 || true
    fi
}

run_in_lxd_container() {
    local src_script input_in_ct output_in_ct cmd_str
    local container_src_root
    local inner_args=()
    local extra_initrd_name extra_kernel_name

    _LXD_CT_NAME="repack-pc-kernel-$(date +%s)-$RANDOM"
    container_src_root=/tmp/snapd-src
    src_script="$container_src_root/tests/lib/repack-pc-kernel-with-initramfs.sh"
    input_in_ct=/tmp/repack-input
    output_in_ct=/tmp/repack-output

    trap cleanup_lxd EXIT

    lxc launch "$LXD_IMAGE" "$_LXD_CT_NAME"
    _LXD_CREATED=true

    lxc exec "$_LXD_CT_NAME" -- bash -lc 'for i in $(seq 1 30); do ping -c1 -W1 1.1.1.1 >/dev/null 2>&1 && exit 0; sleep 1; done; exit 1'
    lxc exec "$_LXD_CT_NAME" -- bash -lc 'mkdir -p /tmp/repack-input /tmp/repack-output /tmp/snapd-src'

    lxc exec "$_LXD_CT_NAME" -- bash -lc 'DEBIAN_FRONTEND=noninteractive apt-get update'
    lxc exec "$_LXD_CT_NAME" -- bash -lc 'DEBIAN_FRONTEND=noninteractive apt-get install -y squashfs-tools snapd binutils initramfs-tools cpio zstd python3 lsb-release eatmydata dpkg-dev debhelper devscripts distro-info software-properties-common linux-firmware golang-go'

    # Copy project sources into container without preserving host ownership.
    tar -C "$PROJECT_PATH" -cf - . | lxc exec "$_LXD_CT_NAME" -- bash -lc "tar -C $container_src_root --no-same-owner -xf -"

    inner_args+=("--inside-lxd")
    inner_args+=("--project-path" "$container_src_root")
    inner_args+=("--core-version" "$CORE_VERSION")
    inner_args+=("--kernel-channel" "$KERNEL_CHANNEL")
    inner_args+=("--arch" "$ARCH")
    inner_args+=("--output-dir" "$output_in_ct")
    inner_args+=("--epoch-bump-time" "$EPOCH_BUMP_TIME")

    if [ "$INJECT_KERNEL_PANIC" = "true" ]; then
        inner_args+=("--inject-kernel-panic")
    fi
    if [ "$GENERATE_COVERAGE" = "true" ]; then
        inner_args+=("--generate-coverage")
    fi

    if [ -n "$INPUT_KERNEL_SNAP" ]; then
        lxc file push "$INPUT_KERNEL_SNAP" "$_LXD_CT_NAME$input_in_ct/input-kernel.snap"
        inner_args+=("--input-kernel-snap" "$input_in_ct/input-kernel.snap")
    fi
    if [ -n "$SNAPD_SNAP" ]; then
        lxc file push "$SNAPD_SNAP" "$_LXD_CT_NAME$input_in_ct/snapd.snap"
        inner_args+=("--snapd-snap" "$input_in_ct/snapd.snap")
    fi
    if [ -n "$EXTRA_INITRD" ]; then
        extra_initrd_name="$(basename "$EXTRA_INITRD")"
        lxc file push -r "$EXTRA_INITRD" "$_LXD_CT_NAME$input_in_ct/"
        inner_args+=("--extra-initrd" "$input_in_ct/$extra_initrd_name")
    fi
    if [ -n "$EXTRA_KERNEL_SNAP" ]; then
        extra_kernel_name="$(basename "$EXTRA_KERNEL_SNAP")"
        lxc file push -r "$EXTRA_KERNEL_SNAP" "$_LXD_CT_NAME$input_in_ct/"
        inner_args+=("--extra-kernel-snap" "$input_in_ct/$extra_kernel_name")
    fi

    printf -v cmd_str '%q ' bash "$src_script" "${inner_args[@]}"
    lxc exec "$_LXD_CT_NAME" -- bash -lc "$cmd_str"

    mkdir -p "$OUTPUT_DIR"
    lxc file pull -r "$_LXD_CT_NAME$output_in_ct/." "$OUTPUT_DIR/"

    trap - EXIT
    cleanup_lxd
}

build_initramfs_deb() (
    pushd "$PROJECT_PATH"/core-initrd >/dev/null

    # Keep this aligned with tests/lib/core-initrd.sh build_initramfs_deb.
    apt-get install -y dpkg-dev debhelper devscripts distro-info eatmydata >/dev/null

    rel=$(lsb_release -r -s)
    TEST_BUILD=1 ./build-source-pkgs.sh "$rel"

    pushd "$rel" >/dev/null
    eatmydata apt-get build-dep -y ./ >/dev/null
    dpkg-buildpackage -tc -us -uc
    popd >/dev/null

    popd >/dev/null
)

build_and_unpack_initramfs_deb() {
    build_initramfs_deb

    quiet eatmydata apt-get install -y "$PROJECT_PATH"/core-initrd/ubuntu-core-initramfs_*.deb

    SNAP_BOOTSTRAP="/usr/lib/snapd/snap-bootstrap"
}

extract_snap_bootstrap_from_snapd_snap() {
    local snapd_snap="$1"
    local out_path="$2"

    unsquashfs -no-progress -f -d "$TMPDIR_WORK/snapd-unpack" "$snapd_snap" usr/lib/snapd/snap-bootstrap >/dev/null
    cp -f "$TMPDIR_WORK/snapd-unpack/usr/lib/snapd/snap-bootstrap" "$out_path"
    chmod 0755 "$out_path"
}

write_bootstrap_wrapper() {
    local skeleton_path="$1"
    local inject_err="$2"

    cp -a "$SNAP_BOOTSTRAP" "$skeleton_path"/usr/lib/snapd/snap-bootstrap.real
    cat <<'EOF' >"$skeleton_path"/usr/lib/snapd/snap-bootstrap
#!/bin/sh
set -eux
if [ "$1" != initramfs-mounts ]; then
    exec /usr/lib/snapd/snap-bootstrap.real "$@"
fi
EOF

    if [ "$GENERATE_COVERAGE" = "true" ]; then
        cat <<'EOF' >>"$skeleton_path"/usr/lib/snapd/snap-bootstrap
bootstrap_coverdir=/run/snapd-bootstrap-gocover
mkdir -p "$bootstrap_coverdir"
chmod 0777 "$bootstrap_coverdir"
export GOCOVERDIR="$bootstrap_coverdir"
echo "spread coverage: initramfs bootstrap GOCOVERDIR=$GOCOVERDIR"
EOF
    fi

    cat <<'EOF' >>"$skeleton_path"/usr/lib/snapd/snap-bootstrap
beforeDate="$(date --utc '+%s')"
/usr/lib/snapd/snap-bootstrap.real "$@"
if [ -d /run/mnt/data/system-data ]; then
    touch /run/mnt/data/system-data/the-tool-ran
fi
if [ -n "${bootstrap_coverdir:-}" ]; then
    d=/run/mnt/ubuntu-seed/go-cover
    if mkdir -p "$d" 2>/dev/null; then
        chmod 0777 "$d" || true
        cp -a "$bootstrap_coverdir"/. "$d"/ 2>/dev/null || true
        echo "spread coverage: initramfs copied coverage to $d"
    fi
fi
mode="$(grep -Eo 'snapd_recovery_mode=([a-z]+)' /proc/cmdline)"
mode=${mode##snapd_recovery_mode=}
mkdir -p /run/mnt/ubuntu-seed/test
stat -c '%Y' /usr/lib/clock-epoch >> /run/mnt/ubuntu-seed/test/${mode}-clock-epoch
echo "$beforeDate" > /run/mnt/ubuntu-seed/test/${mode}-before-snap-bootstrap-date
date --utc '+%s' > /run/mnt/ubuntu-seed/test/${mode}-after-snap-bootstrap-date
EOF

    if [ "$inject_err" = "true" ]; then
        echo "echo 'forcibly panicking'; echo c > /proc/sysrq-trigger" >>"$skeleton_path"/usr/lib/snapd/snap-bootstrap
    fi

    chmod +x "$skeleton_path"/usr/lib/snapd/snap-bootstrap
}

build_uc20_22_kernel_snap() {
    local orig_snap="$1"
    local target_dir="$2"

    unsquashfs -d repacked-kernel "$orig_snap"

    (
        cd repacked-kernel
        local unpackeddir kver skeletondir initrd_dir clock_epoch_file
        unpackeddir="$PWD"
        kver=$(ls config-* | sed -E 's/^config-//')

        objcopy -j .initrd -O binary kernel.efi initrd
        unmkinitramfs initrd unpacked-initrd

        cp -ar unpacked-initrd skeleton
        skeletondir="$PWD/skeleton"
        initrd_dir="$skeletondir/main"
        clock_epoch_file="$skeletondir/main/usr/lib/clock-epoch"

        if [ "$ARCH" = "armhf" ]; then
            initrd_dir="$skeletondir"
            clock_epoch_file="$skeletondir/usr/lib/clock-epoch"
        fi

        write_bootstrap_wrapper "$initrd_dir" "$INJECT_KERNEL_PANIC"

        touch -t "$(date --utc "--date=@$EPOCH_BUMP_TIME" '+%Y%m%d%H%M')" "$clock_epoch_file"

        if [ -n "$EXTRA_INITRD" ]; then
            if [ "$ARCH" = "armhf" ]; then
                cp -a "$EXTRA_INITRD"/* "$skeletondir"
            else
                cp -a "$EXTRA_INITRD"/* "$skeletondir"/main
            fi
        fi

        (
            local feature
            if [ "$ARCH" = "armhf" ]; then
                cd unpacked-initrd
                feature='.'
            else
                cd unpacked-initrd/main
                feature='main'
            fi

            "$INITRAMFS_TOOL" create-initrd \
                --kernelver "$kver" \
                --skeleton "$skeletondir" \
                --kerneldir "${unpackeddir}/modules/$kver" \
                --firmwaredir "${unpackeddir}/firmware" \
                --feature "$feature" \
                --output "${unpackeddir}"/repacked-initrd
        )

        objcopy -j .linux -O binary kernel.efi "vmlinuz-$kver"

        "$INITRAMFS_TOOL" create-efi \
            --kernelver "$kver" \
            --initrd repacked-initrd \
            --kernel vmlinuz \
            --output repacked-kernel.efi

        mv "repacked-kernel.efi-$kver" kernel.efi
        chmod +x kernel.efi

        rm -rf unpacked-initrd skeleton initrd repacked-initrd-* vmlinuz-*
    )

    rm -rf repacked-kernel/firmware/*

    if [ -n "$EXTRA_KERNEL_SNAP" ]; then
        cp -a "$EXTRA_KERNEL_SNAP"/* ./repacked-kernel
    fi

    snap pack repacked-kernel "$target_dir"
    rm -rf repacked-kernel
}

build_uc24_26_kernel_snap() {
    local orig_snap="$1"
    local target_dir="$2"

    unsquashfs -d pc-kernel "$orig_snap"

    local kernelver initrd_f
    kernelver=$(find pc-kernel/modules/ -maxdepth 1 -mindepth 1 -printf "%f")

    "$INITRAMFS_TOOL" create-initrd \
        --kernelver="$kernelver" \
        --kerneldir pc-kernel/modules/"$kernelver" \
        --firmwaredir pc-kernel/firmware \
        --output initrd.img

    # Keep parity with uc24_build_initramfs_kernel_snap in tests/lib/prepare.sh.
    stat manifest-initramfs.yaml-"$kernelver"

    initrd_f=initrd.img-"$kernelver"
    rm -rf initrd
    unmkinitramfs "$initrd_f" initrd

    if [ -n "$EXTRA_INITRD" ]; then
        if [ -d ./initrd/early ]; then
            cp -aT "$EXTRA_INITRD" ./initrd/main
        else
            cp -aT "$EXTRA_INITRD" ./initrd
        fi
    fi

    if [ -d ./initrd/early ]; then
        write_bootstrap_wrapper ./initrd/main "$INJECT_KERNEL_PANIC"

        (cd ./initrd/early; find . | cpio --create --quiet --format=newc --owner=0:0) >"$initrd_f"
        (cd ./initrd/main; find . | cpio --create --quiet --format=newc --owner=0:0 | zstd -1 -T0) >>"$initrd_f"
    else
        write_bootstrap_wrapper ./initrd "$INJECT_KERNEL_PANIC"

        (cd ./initrd; find . | cpio --create --quiet --format=newc --owner=0:0 | zstd -1 -T0) >"$initrd_f"
    fi

    objcopy -O binary -j .linux pc-kernel/kernel.efi linux-"$kernelver"
    "$INITRAMFS_TOOL" create-efi --kernelver="$kernelver" --initrd initrd.img --kernel linux --output kernel.efi
    cp kernel.efi-"$kernelver" pc-kernel/kernel.efi

    if [ -n "$EXTRA_KERNEL_SNAP" ]; then
        cp -a "$EXTRA_KERNEL_SNAP"/* ./pc-kernel
    fi

    snap pack pc-kernel
    mv pc-kernel_*.snap "$target_dir"/
    rm -rf pc-kernel
}

INPUT_KERNEL_SNAP=
SNAPD_SNAP=
OUTPUT_DIR=$(pwd)
CORE_VERSION=24
KERNEL_CHANNEL=stable
ARCH=amd64
SNAP_BOOTSTRAP=
INITRAMFS_TOOL=ubuntu-core-initramfs
USE_LXD_CONTAINER=false
LXD_IMAGE=ubuntu:24.04
INSIDE_LXD=false
INJECT_KERNEL_PANIC=false
GENERATE_COVERAGE=false
EXTRA_INITRD=
EXTRA_KERNEL_SNAP=
EPOCH_BUMP_TIME=$(date '+%s')

while [ $# -gt 0 ]; do
    case "$1" in
        --input-kernel-snap)
            INPUT_KERNEL_SNAP="${2:-}"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="${2:-}"
            shift 2
            ;;
        --snapd-snap)
            SNAPD_SNAP="${2:-}"
            shift 2
            ;;
        --core-version)
            CORE_VERSION="${2:-}"
            shift 2
            ;;
        --kernel-channel)
            KERNEL_CHANNEL="${2:-}"
            shift 2
            ;;
        --use-lxd-container)
            USE_LXD_CONTAINER=true
            shift
            ;;
        --lxd-image)
            LXD_IMAGE="${2:-}"
            shift 2
            ;;
        --inside-lxd)
            INSIDE_LXD=true
            shift
            ;;
        --project-path)
            PROJECT_PATH_OVERRIDE="${2:-}"
            shift 2
            ;;
        --arch)
            ARCH="${2:-}"
            shift 2
            ;;
        --inject-kernel-panic)
            INJECT_KERNEL_PANIC=true
            shift
            ;;
        --generate-coverage)
            GENERATE_COVERAGE="true"
            shift
            ;;
        --extra-initrd)
            EXTRA_INITRD="${2:-}"
            shift 2
            ;;
        --extra-kernel-snap)
            EXTRA_KERNEL_SNAP="${2:-}"
            shift 2
            ;;
        --epoch-bump-time)
            EPOCH_BUMP_TIME="${2:-}"
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

case "$ARCH" in
    amd64|arm64|armhf)
        ;;
    *)
        echo "unsupported --arch: $ARCH" >&2
        exit 1
        ;;
esac

case "$CORE_VERSION" in
    20|22|24|26)
        ;;
    *)
        echo "unsupported --core-version: $CORE_VERSION" >&2
        exit 1
        ;;
esac

if [ -n "$INPUT_KERNEL_SNAP" ]; then
    INPUT_KERNEL_SNAP="$(abspath "$INPUT_KERNEL_SNAP")"
    if [ ! -f "$INPUT_KERNEL_SNAP" ]; then
        echo "input kernel snap not found: $INPUT_KERNEL_SNAP" >&2
        exit 1
    fi
fi
OUTPUT_DIR="$(abspath "$OUTPUT_DIR")"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_PATH="$(cd "$SCRIPT_DIR/../.." && pwd)"
if [ -n "${PROJECT_PATH_OVERRIDE:-}" ]; then
    PROJECT_PATH="$PROJECT_PATH_OVERRIDE"
fi

if [ -n "$SNAPD_SNAP" ]; then
    SNAPD_SNAP="$(abspath "$SNAPD_SNAP")"
fi

if [ -n "$SNAPD_SNAP" ] && [ ! -f "$SNAPD_SNAP" ]; then
    echo "snapd snap not found: $SNAPD_SNAP" >&2
    exit 1
fi
if [ -n "$EXTRA_INITRD" ]; then
    EXTRA_INITRD="$(abspath "$EXTRA_INITRD")"
    [ -d "$EXTRA_INITRD" ] || { echo "extra-initrd dir not found: $EXTRA_INITRD" >&2; exit 1; }
fi
if [ -n "$EXTRA_KERNEL_SNAP" ]; then
    EXTRA_KERNEL_SNAP="$(abspath "$EXTRA_KERNEL_SNAP")"
    [ -d "$EXTRA_KERNEL_SNAP" ] || { echo "extra-kernel-snap dir not found: $EXTRA_KERNEL_SNAP" >&2; exit 1; }
fi

if [ "$USE_LXD_CONTAINER" = "true" ] && [ "$INSIDE_LXD" = "false" ]; then
    require_cmd lxc
    run_in_lxd_container
    echo "Done. Repacked kernel snap in: $OUTPUT_DIR"
    exit 0
fi

require_cmd unsquashfs
require_cmd snap
require_cmd objcopy
require_cmd unmkinitramfs
require_cmd cpio
require_cmd zstd
USE_BOOTSTRAP_FROM_INITRAMFS=false
if [ "$CORE_VERSION" = "24" ] || [ "$CORE_VERSION" = "26" ]; then
    USE_BOOTSTRAP_FROM_INITRAMFS=true
fi
if [ "$USE_BOOTSTRAP_FROM_INITRAMFS" = "true" ]; then
    require_cmd apt-get
    require_cmd lsb_release
    require_cmd dpkg-deb
fi

mkdir -p "$OUTPUT_DIR"
TMPDIR_WORK="$(mktemp -d /tmp/repack-pc-kernel.XXXXXXXX)"
# trap 'rm -rf "$TMPDIR_WORK"' EXIT

if [ -z "$INPUT_KERNEL_SNAP" ]; then
    snap download --basename="pc-kernel" --channel="${CORE_VERSION}/${KERNEL_CHANNEL}" --target-directory="$TMPDIR_WORK" pc-kernel
    INPUT_KERNEL_SNAP="$TMPDIR_WORK"/pc-kernel.snap
fi

if [ "$USE_BOOTSTRAP_FROM_INITRAMFS" = "true" ]; then
    build_and_unpack_initramfs_deb
else
    if [ -n "$SNAPD_SNAP" ]; then
        SNAP_BOOTSTRAP="$TMPDIR_WORK/snap-bootstrap"
        extract_snap_bootstrap_from_snapd_snap "$SNAPD_SNAP" "$SNAP_BOOTSTRAP"
    else
        echo "must supply --snapd-snap for core versions less than 24" >&2
        exit 1
    fi
fi

if ! command -v "$INITRAMFS_TOOL" >/dev/null 2>&1 && [ ! -x "$INITRAMFS_TOOL" ]; then
    echo "cannot resolve ubuntu-core-initramfs tool; use --use-snap-bootstrap-from-initramfs or install it in PATH" >&2
    exit 1
fi

pushd "$TMPDIR_WORK" >/dev/null
if [ "$CORE_VERSION" = "20" ] || [ "$CORE_VERSION" = "22" ]; then
    build_uc20_22_kernel_snap "$INPUT_KERNEL_SNAP" "$OUTPUT_DIR"
else
    build_uc24_26_kernel_snap "$INPUT_KERNEL_SNAP" "$OUTPUT_DIR"
fi
popd >/dev/null

echo "Done. Repacked kernel snap in: $OUTPUT_DIR"
