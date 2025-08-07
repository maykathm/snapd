FROM archlinux

COPY packaging/arch/PKGBUILD /root

RUN pacman -Syu --noconfirm && \
    source /root/PKGBUILD && \
    pacman -Suq --needed --noconfirm \
        ${makedepends[@]} \
        base-devel

RUN useradd test -m
