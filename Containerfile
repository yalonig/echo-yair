# syntax=docker/dockerfile:1
# Drop-in rebuild of nginx:1.25-bookworm: nginx and its four dynamic modules
# compiled from source (build/), installed as .debs on a clean Debian base, with
# the upstream image's startup *scripts* reused verbatim. No upstream binaries.
ARG UPSTREAM_IMAGE=nginx:1.25-bookworm
ARG BASE_IMAGE=debian:bookworm-slim

# Source only the Docker entrypoint shell scripts from the upstream image.
FROM ${UPSTREAM_IMAGE} AS upstream

FROM ${BASE_IMAGE}
LABEL org.opencontainers.image.title="echo-nginx"
LABEL org.opencontainers.image.description="Drop-in rebuild of nginx:1.25-bookworm, built from source with CVE-2026-15176 backported"

# Recreate the nginx user exactly as upstream: uid/gid 101, comment, home, shell.
RUN set -eux; \
    groupadd --system --gid 101 nginx; \
    useradd --system --gid nginx --no-create-home --home /nonexistent \
            --comment "nginx user" --shell /bin/false --uid 101 nginx

# Install everything we compiled: nginx (with the backport), its four dynamic
# modules (geoip, image-filter, njs, xslt) and the version-bumped PCRE2. apt
# resolves their runtime libraries from the packages' own Depends (libssl3,
# libgd3, libxml2, libxslt1.1, libgeoip1, ...). The rest mirrors the upstream
# image's install line: gettext-base and curl, plus ca-certificates and tzdata.
COPY dist/nginx_*.deb dist/nginx-module-*.deb dist/libpcre2-8-0_*.deb /tmp/
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       /tmp/libpcre2-8-0_*.deb /tmp/nginx_*.deb /tmp/nginx-module-*.deb \
       gettext-base curl ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/* /tmp/*.deb

# Build gate. FAILS the build unless:
#  - nginx, all four modules and PCRE2 are OUR from-source packages (+echo1),
#    so an upstream or distro binary can never silently stand in for them;
#  - PCRE2 and OpenSSL are at or above their CVE-fixed versions.
RUN set -eux; \
    for p in nginx nginx-module-geoip nginx-module-image-filter \
             nginx-module-njs nginx-module-xslt libpcre2-8-0; do \
      v="$(dpkg-query -W -f='${Version}' "$p")"; \
      case "$v" in *+echo1) ;; *) echo "not our build: $p $v" >&2; exit 1 ;; esac; \
    done; \
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libpcre2-8-0)" ge '10.42-1+deb12u1'; \
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libssl3)" ge '3.0.15-1~deb12u1'

# Forward access/error logs to the container's stdout/stderr, like upstream.
RUN ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log

# Reuse the upstream startup glue (shell scripts) verbatim so boot behaviour is identical.
COPY --from=upstream /docker-entrypoint.sh /docker-entrypoint.sh
COPY --from=upstream /docker-entrypoint.d /docker-entrypoint.d
RUN chmod +x /docker-entrypoint.sh /docker-entrypoint.d/*.sh

# Same variables as upstream; the release values carry our +echo1 suffix because
# they describe the packages actually installed (ours).
ENV NGINX_VERSION=1.25.5 \
    NJS_VERSION=0.8.4 \
    NJS_RELEASE=3~bookworm+echo1 \
    PKG_RELEASE=1~bookworm+echo1
EXPOSE 80
STOPSIGNAL SIGQUIT
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
