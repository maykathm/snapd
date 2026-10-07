#!/bin/bash

tag=$(date +%Y-%m-%d)

for image in snapd-fakestore snapd-testing-image snapd-run-on-host; do
    docker tag "$image":latest us-central1-docker.pkg.dev/molten-verve-216720/canonical-repository/"$image":"$tag"
    docker push us-central1-docker.pkg.dev/molten-verve-216720/canonical-repository/"$image":"$tag"
done
