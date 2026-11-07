#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=/dev/null
source versions.env

shopt -s nullglob
debs=(dist/nginx_*.deb)
if [ "${#debs[@]}" -eq 0 ]; then
  echo "No nginx .deb in dist/. Run 'make deb' first." >&2
  exit 1
fi
pcre=(dist/libpcre2-8-0_*.deb)
if [ "${#pcre[@]}" -eq 0 ]; then
  echo "No PCRE2 .deb in dist/. Run 'make pcre2' first." >&2
  exit 1
fi

upstream="${UPSTREAM_IMAGE}"
[ -n "${UPSTREAM_DIGEST:-}" ] && upstream="${UPSTREAM_IMAGE}@${UPSTREAM_DIGEST}"
base="${BUILD_BASE_IMAGE}"
[ -n "${BUILD_BASE_DIGEST:-}" ] && base="${BUILD_BASE_IMAGE}@${BUILD_BASE_DIGEST}"

image="echo-nginx:${NGINX_VERSION}"
docker build \
  --build-arg UPSTREAM_IMAGE="$upstream" \
  --build-arg BASE_IMAGE="$base" \
  -f Containerfile -t "$image" .

printf '\nBuilt %s\n' "$image"
printf 'Image sizes (original vs ours):\n'
docker images "${UPSTREAM_IMAGE}" --format '  {{.Repository}}:{{.Tag}}  {{.Size}}'
docker images "$image" --format '  {{.Repository}}:{{.Tag}}  {{.Size}}'
