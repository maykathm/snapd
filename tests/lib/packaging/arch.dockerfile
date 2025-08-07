FROM archlinux

COPY packaging/arch/PKGBUILD .

RUN pacman -Syu --noconfirm && \
    pacman -Suq --needed --noconfirm \
        ${makedepends[@]} \
        ${checkdepends[@]}

RUN useradd test -m
