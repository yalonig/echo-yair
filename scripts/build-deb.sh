#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=/dev/null
source versions.env

image="echo-nginx-build:${NGINX_VERSION}"
base="${BUILD_BASE_IMAGE}"
if [ -n "${BUILD_BASE_DIGEST:-}" ]; then
  base="${BUILD_BASE_IMAGE}@${BUILD_BASE_DIGEST}"
fi

docker build \
  --build-arg BASE_IMAGE="$base" \
  --build-arg NGINX_VERSION="$NGINX_VERSION" \
  --build-arg NGINX_SHA512="$NGINX_SHA512" \
  --build-arg NJS_VERSION="$NJS_VERSION" \
  --build-arg NJS_GITHUB_SHA512="$NJS_GITHUB_SHA512" \
  --build-arg PKG_OSS_REF="$PKG_OSS_REF" \
  --build-arg PKG_OSS_COMMIT="$PKG_OSS_COMMIT" \
  -f build/Dockerfile -t "$image" build

mkdir -p dist
cid="$(docker create "$image")"
trap 'docker rm -f "$cid" >/dev/null 2>&1 || true; docker image rm "$image" >/dev/null 2>&1 || true' EXIT
# Clear this step's previous outputs first, so a stale package (e.g. an older
# module release) can never sit next to the fresh one and get installed.
rm -f dist/nginx_*.deb dist/nginx-module-*.deb dist/nginx-V.txt
docker cp "$cid:/out/." dist/
printf '\nArtifacts in dist/:\n'
ls -la dist/
