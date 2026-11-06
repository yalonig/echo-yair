# syntax=docker/dockerfile:1
ARG BASE_IMAGE=debian:bookworm-slim
FROM ${BASE_IMAGE}

ARG NGINX_VERSION
ARG NGINX_SHA512
ARG PKG_OSS_REF
ARG PKG_OSS_COMMIT
ARG PKG_VERSION
ENV NGINX_VERSION=${NGINX_VERSION} \
    NGINX_SHA512=${NGINX_SHA512} \
    PKG_OSS_REF=${PKG_OSS_REF} \
    PKG_OSS_COMMIT=${PKG_OSS_COMMIT} \
    PKG_VERSION=${PKG_VERSION} \
    PATCH_DIR=/patches \
    OUT_DIR=/out \
    DEBIAN_FRONTEND=noninteractive

# Build toolchain + nginx Build-Depends (libssl-dev, libpcre2-dev, zlib1g-dev).
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git \
      build-essential dpkg-dev debhelper devscripts quilt lsb-release xsltproc \
      libssl-dev libpcre2-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY patches/ /patches/
COPY build.sh /usr/local/bin/build.sh
RUN chmod +x /usr/local/bin/build.sh && /usr/local/bin/build.sh
