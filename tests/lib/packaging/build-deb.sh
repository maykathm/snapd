#!/bin/bash

set -e

snapd_dir=$1
user=$2
pkg_dir=$3

cd "$snapd_dir"

dch --newversion "$(cat "$pkg_dir/version")" "testing build"
unshare -n -- \
    su -l -c "cd $snapd_dir && DEB_BUILD_OPTIONS='nocheck testkeys' dpkg-buildpackage -tc -b -Zgzip -uc -us" "$user"
