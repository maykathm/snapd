FROM fedora:42

RUN dnf makecache && \
    dnf update -y && \
    dnf -y --refresh install --setopt=install_weak_deps=False mock go git fakeroot

RUN useradd mockbuilder && usermod -a -G mock mockbuilder

USER mockbuilder
