# syntax=docker/dockerfile:1

##
## Builder stage: build Python venv + prepare app assets
##
FROM ubuntu:24.04 AS builder

# uv by default targets a project-local `.venv`. We want it to install into the
# Docker venv at /opt/venv and NEVER create/target /app/autocaliweb/.venv.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG BUILD_DATE
ARG BUILD_ID
ARG VERSION
ARG DEBIAN_FRONTEND=noninteractive

# Choose the Python version for the venv (runtime uses the same venv)
ARG PYTHON_VERSION=3.13

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

WORKDIR /app/autocaliweb

# Build dependencies (only in builder) + install newer Python via deadsnakes PPA
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      software-properties-common \
      ca-certificates \
      curl \
      git \
    ; \
    add-apt-repository -y ppa:deadsnakes/ppa; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      build-essential \
      python${PYTHON_VERSION} \
      python${PYTHON_VERSION}-dev \
      python${PYTHON_VERSION}-venv \
      python3-pip \
      libldap2-dev \
      libsasl2-dev \
      zip \
    ; \
    \
    # Ensure native extensions can compile against the selected interpreter
    # (e.g. python-ldap needs Python.h from python${PYTHON_VERSION}-dev).
    test -f "/usr/include/python${PYTHON_VERSION}/Python.h" || (echo "Missing Python headers for python${PYTHON_VERSION} (expected /usr/include/python${PYTHON_VERSION}/Python.h)"; exit 1); \
    rm -rf /var/lib/apt/lists/*

# Copy dependency manifests first to maximize layer cache hits
# Canonical dependency install: uv.lock + pyproject.toml
COPY pyproject.toml uv.lock ./

# Create venv + install uv (but DON'T sync yet: uv's default behavior may try to
# build metadata for the local project, which fails before the source is copied)
RUN --mount=type=cache,target=/root/.cache/uv \
    set -eux; \
    python${PYTHON_VERSION} -m venv /opt/venv; \
    /opt/venv/bin/python -m pip install -U pip wheel; \
    /opt/venv/bin/pip install -U uv

# Copy the full application source
COPY . .

# Preflight: ensure the checked-in uv.lock matches pyproject.toml for this source tree.
# If it doesn't, fail fast with a clear message instead of attempting to proceed.
RUN set -eux; \
    . /opt/venv/bin/activate; \
    uv --directory /app/autocaliweb lock --check

# Now that the source is present, sync deps from the checked-in lock (extras included)
RUN --mount=type=cache,target=/root/.cache/uv \
    set -eux; \
    . /opt/venv/bin/activate; \
    uv --directory /app/autocaliweb sync --locked --no-install-project --all-extras

# Build KOReader plugin zip (kept as-is, including BUILD_DATE in digest file)
RUN set -eux; \
    cd /app/autocaliweb/koreader/plugins; \
    PLUGIN_DIGEST="$(find acwsync.koplugin -type f \( -name '*.lua' -o -name '*.json' \) | sort | xargs sha256sum | sha256sum | cut -d' ' -f1)"; \
    { \
      echo "Plugin files digest: ${PLUGIN_DIGEST}"; \
      echo "Build date: ${BUILD_DATE:-}"; \
      echo "Files included:"; \
      find acwsync.koplugin -type f \( -name '*.lua' -o -name '*.json' \) | sort; \
    } >> "acwsync.koplugin/${PLUGIN_DIGEST}.digest"; \
    zip -r koplugin.zip acwsync.koplugin/; \
    cp koplugin.zip /app/autocaliweb/cps/static

# Write version marker (used later)
RUN set -eux; \
    echo "${VERSION:-}" >| /app/ACW_RELEASE


##
## Runtime stage: minimal runtime packages + binaries + app + venv
##
FROM ubuntu:24.04 AS runtime

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG BUILD_DATE
ARG BUILD_ID
ARG VERSION
ARG DEBIAN_FRONTEND=noninteractive

# Keep runtime aligned with builder venv Python version
ARG PYTHON_VERSION=3.13

LABEL org.opencontainers.image.created="${BUILD_DATE}" \
    org.opencontainers.image.version="${VERSION}" \
    org.opencontainers.image.source="https://github.com/gelbphoenix/autocaliweb" \
    org.opencontainers.image.licences="GPL-3.0" \
    org.opencontainers.image.authors="gelbphoenix" \
    org.opencontainers.image.title="Autocaliweb" \
    org.opencontainers.image.description="Web managing platform for eBooks, eComics and PDFs" \
    de.gelbphoenix.autocaliweb.buildid="${BUILD_ID}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    CALIBRE_DBPATH=/config \
    UMASK=0002 \
    S6_STAGE2_HOOK=/docker-mods \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app/autocaliweb
USER root

# Create the abc user
RUN set -eux; \
    useradd -u 911 -U -d /config -s /bin/false abc; \
    usermod -G users abc

# Runtime dependencies only (+ install newer Python via deadsnakes PPA for the venv interpreter)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      software-properties-common \
      ca-certificates \
      curl \
    ; \
    add-apt-repository -y ppa:deadsnakes/ppa; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      # runtime python (matches venv interpreter)
      python${PYTHON_VERSION} \
      # app runtime libs
      imagemagick \
      ghostscript \
      libldap2 \
      libsasl2-2 \
      libmagic1 \
      libxslt1.1 \
      sqlite3 \
      xz-utils \
      xdg-utils \
      tzdata \
      inotify-tools \
      netcat-openbsd \
      binutils \
      fonts-dejavu-core \
      # calibre GUI deps (headless)
      libxi6 \
      libxtst6 \
      libxrandr2 \
      libxkbfile1 \
      libxcomposite1 \
      libopengl0 \
      libnss3 \
      libxkbcommon0 \
      libegl1 \
      libxdamage1 \
      libgl1 \
      libglx-mesa0 \
      # calibre qtwebengine (prevents libasound.so.2 missing warnings)
      libasound2t64 \
    ; \
    rm -rf /var/lib/apt/lists/*

# Bring in venv and app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/autocaliweb /app/autocaliweb
COPY --from=builder /app/ACW_RELEASE /app/ACW_RELEASE

# To ensure that docker-mods for calibre-web can be used
RUN set -eux; \
    ln -s /app/autocaliweb /app/calibre-web

# Install rootfs overlay and run app setup (kept from original)
RUN set -eux; \
    cp -r /app/autocaliweb/root/* /; \
    rm -rf /app/autocaliweb/root/; \
    /app/autocaliweb/scripts/setup-acw.sh

# Install S6-Overlay (floating latest, but hardened curl and cleanup)
RUN set -eux; \
    S6_OVERLAY_VERSION="$(curl -fsSL --retry 3 --retry-delay 2 https://api.github.com/repos/just-containers/s6-overlay/releases/latest | sed -nE 's/^[[:space:]]*"tag_name":[[:space:]]*"([^"]+)".*/\1/p' | head -n1)"; \
    test -n "${S6_OVERLAY_VERSION}"; \
    ARCH="$(uname -m | sed 's/x86_64/x86_64/;s/aarch64/aarch64/')"; \
    curl -fsSL --retry 3 --retry-delay 2 \
      -o "/tmp/s6-overlay-${ARCH}.tar.xz" \
      "https://github.com/just-containers/s6-overlay/releases/download/${S6_OVERLAY_VERSION}/s6-overlay-${ARCH}.tar.xz"; \
    curl -fsSL --retry 3 --retry-delay 2 \
      -o /tmp/s6-overlay-noarch.tar.xz \
      "https://github.com/just-containers/s6-overlay/releases/download/${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz"; \
    tar -C / -Jxpf "/tmp/s6-overlay-${ARCH}.tar.xz"; \
    tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz; \
    rm -f "/tmp/s6-overlay-${ARCH}.tar.xz" /tmp/s6-overlay-noarch.tar.xz

# Install kepubify (floating latest, but hardened curl)
RUN set -eux; \
    KEPUBIFY_RELEASE="$(curl -fsSL --retry 3 --retry-delay 2 https://api.github.com/repos/pgaskin/kepubify/releases/latest | sed -nE 's/^[[:space:]]*"tag_name":[[:space:]]*"([^"]+)".*/\1/p' | head -n1)"; \
    test -n "${KEPUBIFY_RELEASE}"; \
    KEPUBIFY_ARCH="$(uname -m | sed 's/x86_64/64bit/;s/aarch64/arm64/')"; \
    curl -fsSL --retry 3 --retry-delay 2 \
      -o /usr/bin/kepubify \
      "https://github.com/pgaskin/kepubify/releases/download/${KEPUBIFY_RELEASE}/kepubify-linux-${KEPUBIFY_ARCH}"; \
    chmod +x /usr/bin/kepubify; \
    echo "${KEPUBIFY_RELEASE}" >| /app/KEPUBIFY_RELEASE

# Install Calibre binaries (floating latest, but hardened curl and cleanup)
RUN set -eux; \
    mkdir -p /app/calibre; \
    CALIBRE_RELEASE="$(curl -fsSL --retry 3 --retry-delay 2 https://api.github.com/repos/kovidgoyal/calibre/releases/latest | sed -nE 's/^[[:space:]]*"tag_name":[[:space:]]*"([^"]+)".*/\1/p' | head -n1)"; \
    test -n "${CALIBRE_RELEASE}"; \
    CALIBRE_VERSION="${CALIBRE_RELEASE#v}"; \
    CALIBRE_ARCH="$(uname -m | sed 's/x86_64/x86_64/;s/aarch64/arm64/')"; \
    curl -fsSL --retry 3 --retry-delay 2 \
      -o /tmp/calibre.txz \
      -L "https://download.calibre-ebook.com/${CALIBRE_VERSION}/calibre-${CALIBRE_VERSION}-${CALIBRE_ARCH}.txz"; \
    tar xf /tmp/calibre.txz -C /app/calibre; \
    rm -f /tmp/calibre.txz; \
    /app/calibre/calibre_postinstall || true; \
    echo "${CALIBRE_RELEASE}" >| /app/CALIBRE_RELEASE

# Ensure Calibre CLI tools are discoverable by the app
ENV PATH="/app/calibre:${PATH}"

# Bring in unrar (kept floating latest as in original)
COPY --from=ghcr.io/linuxserver/unrar:latest /usr/bin/unrar-ubuntu /usr/bin/unrar

EXPOSE 8083
VOLUME ["/config", "/acw-book-ingest", "/calibre-library"]

HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=2 \
    CMD curl --fail -m 5 http://localhost:8083/health || exit 1

CMD ["/init"]
