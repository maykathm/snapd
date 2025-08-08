#!/bin/bash

set -e

snapd_dir=$1
user=$2
build_dir=$3

cd "$snapd_dir"

cp -av packaging/arch/* "$build_dir"
chown -R "$user":"$user" "$build_dir"
unshare -n -- \
        su -l -c "cd $build_dir && WITH_TEST_KEYS=1 makepkg -f --nocheck" "$user"