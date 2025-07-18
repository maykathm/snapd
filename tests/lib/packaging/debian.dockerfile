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
    gdebi-core \
    golang-${GOLANG_VERSION}

COPY ./debian/control control

RUN xargs -r eatmydata apt-get install -y $(gdebi --quiet --apt-line control)