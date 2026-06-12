#!/bin/bash

# remove stripping
sed -i '/minidebuginfo/d' build-aux/snap/snapcraft.yaml

# patch builds to include coverage
sed -i '/go build/ { / -cover/! s/go build/go build -cover -covermode=atomic/ }' build-aux/snap/snapcraft.yaml
sed -i '/^EXTRA_GO_BUILD_FLAGS = / { / -cover/! s/$/ -cover -covermode=atomic/ }' packaging/arch/PKGBUILD
find packaging -type f -name snapd.spec -exec sed -i '/^EXTRA_GO_BUILD_FLAGS = / { / -cover/! s/$/ -cover -covermode=atomic/ }' {} \;
