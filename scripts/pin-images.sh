#!/usr/bin/env bash
set -euo pipefail

source versions.env

digest_of() {
  local image="$1"
  docker image inspect --format '{{index .RepoDigests 0}}' "$image" | cut -d@ -f2
}

set_value() {
  local key="$1" value="$2"
  sed -i "s|^${key}=.*|${key}=${value}|" versions.env
}

# Pull outside command substitution, where bash ignores `set -e`.
docker pull --quiet "$UPSTREAM_IMAGE" >/dev/null
docker pull --quiet "$BUILD_BASE_IMAGE" >/dev/null

upstream_digest="$(digest_of "$UPSTREAM_IMAGE")"
base_digest="$(digest_of "$BUILD_BASE_IMAGE")"
set_value UPSTREAM_DIGEST "$upstream_digest"
set_value BUILD_BASE_DIGEST "$base_digest"

printf 'Pinned %s to %s\n' "$UPSTREAM_IMAGE" "$upstream_digest"
printf 'Pinned %s to %s\n' "$BUILD_BASE_IMAGE" "$base_digest"
docker run --rm "$UPSTREAM_IMAGE" nginx -v
