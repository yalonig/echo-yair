#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=/dev/null
source versions.env

base="${BUILD_BASE_IMAGE}"
if [ -n "${BUILD_BASE_DIGEST:-}" ]; then
  base="${BUILD_BASE_IMAGE}@${BUILD_BASE_DIGEST}"
fi

image="echo-pcre2-build:bookworm"
docker build --build-arg BASE_IMAGE="$base" -f build/Dockerfile.pcre2 -t "$image" build

mkdir -p dist
cid="$(docker create "$image")"
trap 'docker rm -f "$cid" >/dev/null 2>&1 || true; docker image rm "$image" >/dev/null 2>&1 || true' EXIT
# Clear this step's previous outputs first, so a stale package (e.g. an older
# module release) can never sit next to the fresh one and get installed.
rm -f dist/libpcre2-8-0_*.deb
docker cp "$cid:/out/." dist/
printf '\nVersion-bumped PCRE2 package in dist/:\n'
ls -la dist/libpcre2-8-0_*.deb
