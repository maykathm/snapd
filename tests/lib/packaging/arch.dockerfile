FROM archlinux

RUN pacman -Syu --noconfirm && \
    pacman pacman -Suq --needed --noconfirm \
        base-devel \
        git

RUN useradd test -m