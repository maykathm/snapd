FROM archlinux

RUN pacman -Syu --noconfirm && \
    pacman pacman -Suq --needed --noconfirm \
        debugedit \
        fakeroot \
        git \
        go \
        go-tools \
        xfsprogs \
        python-docutils \
        apparmor \
        autoconf-archive \
        squashfs-tools \
        base-devel \
        makepkg

RUN useradd test -m