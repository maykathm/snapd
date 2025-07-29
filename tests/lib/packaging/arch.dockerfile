FROM archlinux

RUN pacman -Syu --noconfirm && \
    pacman pacman -Suq --needed --noconfirm \
        squashfs-tools \
        apparmor \
        go-tools \
        xfsprogs \
        python-docutils \
        autoconf-archive \
        base-devel \
        git

RUN curl https://dl.google.com/go/go1.18.10.linux-amd64.tar.gz -O && \
     tar -C /usr/local -xzf go1.18.10.linux-amd64.tar.gz

RUN useradd test -m

ENV PATH=$PATH:/usr/local/go/bin
