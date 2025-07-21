ARG SYSTEM
ARG TAG
ARG GOLANG_VERSION
FROM ${SYSTEM}:${TAG}

ARG GOLANG_VERSION
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get upgrade -y
RUN apt-get install -y \
    sbuild \
    devscripts \
    eatmydata \
    gdebi-core && \
    apt-get install -y golang-${GOLANG_VERSION} || true 

COPY ./debian/control control

RUN gdebi --quiet --apt-line control > deps.txt && \
    xargs -r eatmydata apt-get install -y < deps.txt

RUN if [ -z "$(command -v go)" ]; then \
        ln -s "/usr/lib/go-${GOLANG_VERSION}/bin/go" /usr/bin/go; \
    fi