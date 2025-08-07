FROM archlinux

COPY packaging/arch/PKGBUILD .

RUN pacman -S ${makedepends[@]}

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
