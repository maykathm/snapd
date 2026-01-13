ARG IMAGE=archlinux
ARG TAG=2
ARG PACKAGING_DIR
FROM ${IMAGE}:${TAG}

RUN dnf makecache && \
    dnf update -y && \
    dnf -y --refresh install --setopt=install_weak_deps=False rpm-build rpmdevtools go git

ARG PACKAGING_DIR
COPY packaging/${PACKAGING_DIR}/snapd.spec .

RUN dnf -y --refresh install --setopt=install_weak_deps=False $(rpmspec -q --buildrequires snapd.spec)