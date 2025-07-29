FROM archlinux

RUN pacman -Syu --noconfirm && \
    pacman pacman -Suq --needed --noconfirm \
        squashfs-tools \
        apparmor \
        go \
        go-tools \
        xfsprogs \
        python-docutils \
        autoconf-archive \
        base-devel \
        git

RUN useradd test -m