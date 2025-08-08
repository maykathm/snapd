#!/bin/bash

set -e

pkg=$1
vendor_tar_dir=$2
config_file=/etc/mock/"$3".cfg

src_dir=/tmp/sources

mkdir "$src_dir"

version=$(cat "$vendor_tar_dir"/version)
packaging_path=packaging/"$pkg"

sed -i -e "s/^Version:.*$/Version: $version/g" "$packaging_path/snapd.spec"
sed -i -e "s/^BuildRequires:.*fakeroot/# BuildRequires: fakeroot/" "$packaging_path/snapd.spec"

cp "$packaging_path"/* "$src_dir"
cp "$vendor_tar_dir"/* "$src_dir"

mock -r "$config_file" --install git

mock -r "$config_file" \
    --buildsrpm \
    --with testkeys \
    --spec "$src_dir/snapd.spec" \
    --sources "$src_dir"

mock -r "$config_file" \
    --no-clean \
    --no-cleanup-after \
    --enable-network \
    --nocheck \
    --with testkeys \
    --resultdir /home/mockbuilder/builds
