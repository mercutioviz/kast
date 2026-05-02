# syntax=docker/dockerfile:1.7
# Multi-stage Dockerfile for kast.
#
# Stage 1 (builder) — installs kast and its Python dependencies into a venv
# using full build tooling. Stage 2 (runtime) — slim image that copies the
# venv plus the scanner CLIs and provides `kast` as the entrypoint.
#
# Build:    docker build -t kast:3.0.0 -t kast:latest .
# Run:      docker run --rm -v "$HOME/kast_results:/kast_results" kast:latest \
#               scan --target example.com --output-dir /kast_results
#
# ZAP is NOT bundled. Use kast in --mode passive (default) or run ZAP
# separately and point kast at it via remote mode (--set zap.execution_mode
# =remote --set zap.remote.url=...). See kast-web for managed cloud-mode
# scans.

ARG PYTHON_VERSION=3.13


# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# weasyprint + lxml + pillow build deps. We install build-essential so
# any wheel-less C extensions compile; the slim runtime image doesn't
# carry these.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libfribidi0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        libssl-dev \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml VERSION README.md LICENSE ./
COPY kast/ ./kast/

RUN python -m venv /opt/kast-venv \
    && /opt/kast-venv/bin/pip install --upgrade pip wheel \
    && /opt/kast-venv/bin/pip install .


# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/kast-venv/bin:${PATH}"

# Runtime-only system packages:
#  - WeasyPrint runtime libs (no -dev variants)
#  - Fonts so PDF reports render with non-Latin glyphs
#  - Scanner CLIs that kast plugins shell out to:
#      sslscan, wafw00f, testssl.sh, whatweb
#  - Docker CLI is intentionally NOT installed; ZAP local-mode users mount
#    /var/run/docker.sock and rely on the host's Docker daemon.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libfribidi0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        fonts-noto-core \
        fonts-noto-color-emoji \
        fonts-dejavu \
        sslscan \
        wafw00f \
        whatweb \
        testssl.sh \
    && rm -rf /var/lib/apt/lists/*

# Copy the prebuilt venv from the builder stage.
COPY --from=builder /opt/kast-venv /opt/kast-venv

# Non-root runtime user.
RUN groupadd --gid 1000 kast \
    && useradd --uid 1000 --gid kast --shell /bin/bash --create-home kast \
    && mkdir -p /kast_results /home/kast/.config/kast \
    && chown -R kast:kast /kast_results /home/kast/.config

USER kast
WORKDIR /home/kast
VOLUME ["/kast_results"]

ENV KAST_RESULTS_DIR=/kast_results

ENTRYPOINT ["kast"]
CMD ["--help"]
