FROM archlinux

COPY packaging/arch/* .

RUN pacman -Syu --noconfirm && \
    pacman -Suq --needed --noconfirm \
        ${makedepends[@]} \
        ${checkdepends[@]}

# RUN pacman -Syu --noconfirm && \
#     pacman pacman -Suq --needed --noconfirm \
#         git \
#         go \
#         go-tools \
#         xfsprogs \
#         python-docutils \
#         apparmor \
#         autoconf-archive \
#         squashfs-tools \
#         base-devel

RUN useradd test -m
