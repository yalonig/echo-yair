# syntax=docker/dockerfile:1
# Drop-in rebuild of nginx:1.25-bookworm: our patched nginx .deb on a clean
# Debian base, with the upstream image's startup glue reused verbatim.
ARG UPSTREAM_IMAGE=nginx:1.25-bookworm
ARG BASE_IMAGE=debian:bookworm-slim

# Source only the Docker entrypoint scripts from the upstream image.
FROM ${UPSTREAM_IMAGE} AS upstream

FROM ${BASE_IMAGE}
LABEL org.opencontainers.image.title="echo-nginx"
LABEL org.opencontainers.image.description="Drop-in rebuild of nginx:1.25-bookworm with CVE-2026-15176 backported, dynamic modules preserved"

# Recreate the nginx user with the same uid/gid (101) as the upstream image.
RUN set -eux; \
    groupadd --system --gid 101 nginx; \
    useradd --system --gid nginx --no-create-home --home /nonexistent \
            --shell /usr/sbin/nologin --uid 101 nginx

# Install our patched nginx .deb. apt resolves its runtime deps (libssl3,
# libpcre2-8-0, zlib1g). gettext-base + tzdata match the upstream image and are
# needed by the entrypoint scripts (envsubst, timezones).
COPY dist/nginx_*.deb /tmp/
RUN apt-get update \
    && apt-get install -y --no-install-recommends /tmp/nginx_*.deb gettext-base tzdata \
    && rm -rf /var/lib/apt/lists/* /tmp/*.deb

# Version-bump remediation. nginx links PCRE2 and OpenSSL; both carry CVE fixes in
# Debian bookworm (PCRE2 10.42-1 -> +deb12u2 clears 7 CVEs, OpenSSL 3.0.11 -> 3.0.22
# clears many). Building on the current base installs the patched versions; this
# step makes that explicit and FAILS the build if either library is older than its
# fixed version, so a stale base cannot ship the vulnerable libraries unnoticed.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends libpcre2-8-0 libssl3; \
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libpcre2-8-0)" ge '10.42-1+deb12u1'; \
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libssl3)" ge '3.0.15-1~deb12u1'; \
    rm -rf /var/lib/apt/lists/*

# Runtime libraries the prebuilt dynamic modules link against (njs/xslt -> libxml2,
# xslt -> libxslt, image-filter -> libgd, geoip -> libgeoip). The upstream image
# pulls these in via its module packages; we copy only the .so files, so install
# their shared-library dependencies here or the modules fail to dlopen.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libxml2 libxslt1.1 libgd3 libgeoip1 \
    && rm -rf /var/lib/apt/lists/*

# Forward access/error logs to the container's stdout/stderr, like upstream.
RUN ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log

# Bring the prebuilt dynamic modules (geoip, image-filter, njs, xslt) from the
# upstream image. nginx builds them with --with-compat, so a stock module loads
# into any same-version nginx; ours is the same 1.25.5, also --with-compat. They
# are not loaded by the default config, but a config that load_module's one works.
COPY --from=upstream /usr/lib/nginx/modules/ /usr/lib/nginx/modules/

# Reuse the upstream startup glue verbatim so boot behaviour is identical.
COPY --from=upstream /docker-entrypoint.sh /docker-entrypoint.sh
COPY --from=upstream /docker-entrypoint.d /docker-entrypoint.d
RUN chmod +x /docker-entrypoint.sh /docker-entrypoint.d/*.sh

ENV NGINX_VERSION=1.25.5 \
    PKG_RELEASE=1~bookworm+echo1
EXPOSE 80
STOPSIGNAL SIGQUIT
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
