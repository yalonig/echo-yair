# syntax=docker/dockerfile:1
ARG BASE_IMAGE=debian:bookworm-slim
FROM ${BASE_IMAGE}

ARG NGINX_VERSION
ARG NGINX_SHA512
ARG NJS_VERSION
ARG NJS_GITHUB_SHA512
ARG PKG_OSS_REF
ARG PKG_OSS_COMMIT
ENV NGINX_VERSION=${NGINX_VERSION} \
    NGINX_SHA512=${NGINX_SHA512} \
    NJS_VERSION=${NJS_VERSION} \
    NJS_GITHUB_SHA512=${NJS_GITHUB_SHA512} \
    PKG_OSS_REF=${PKG_OSS_REF} \
    PKG_OSS_COMMIT=${PKG_OSS_COMMIT} \
    PATCH_DIR=/patches \
    OUT_DIR=/out \
    DEBIAN_FRONTEND=noninteractive

# Build toolchain + nginx Build-Depends (libssl-dev, libpcre2-dev, zlib1g-dev),
# plus what pkg-oss needs to build the four dynamic modules from source:
#   geoip -> libgeoip-dev, image-filter -> libgd-dev, xslt -> libxslt1-dev,
#   njs -> libxml2-dev libxslt1-dev libedit-dev (+ xz-utils/file for its sources).
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git file xz-utils \
      build-essential dpkg-dev debhelper devscripts quilt lsb-release xsltproc \
      libssl-dev libpcre2-dev zlib1g-dev \
      libgeoip-dev libgd-dev libxslt1-dev libxml2-dev libedit-dev \
    && rm -rf /var/lib/apt/lists/*

COPY patches/ /patches/
COPY build.sh /usr/local/bin/build.sh
RUN chmod +x /usr/local/bin/build.sh && /usr/local/bin/build.sh
