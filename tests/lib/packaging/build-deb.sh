#!/bin/bash

set -e

snapd_dir=$1
user=$2
buildopt=$3

cd "$snapd_dir"
go mod vendor
su -c "cd $snapd_dir/c-vendor && ./vendor.sh" "$user"

dch --newversion "$(cat "$vendor_tar_dir"/version)" "testing build"
unshare -n -- \
    su -l -c "cd $snapd_dir && DEB_BUILD_OPTIONS='nocheck testkeys ${buildopt}' dpkg-buildpackage -tc -b -Zgzip -uc -us" "$user"
