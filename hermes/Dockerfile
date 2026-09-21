# Hermes Agent is pinned to the requested stable release.
FROM nousresearch/hermes-agent:v2026.6.5

# Provide Node.js/npm for Node-based tools and skills used by the assistant,
# plus the tools needed to install the pinned RTK release.
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl nodejs npm tar \
    && rm -rf /var/lib/apt/lists/*

# RTK is installed in the Hermes image (not the Gateway image). There is no
# amd64 GNU archive in this release, so amd64 uses the official static musl
# archive; arm64 uses the official GNU archive.
ARG TARGETARCH
ARG RTK_VERSION=0.49.0
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      amd64) RTK_TARBALL='rtk-x86_64-unknown-linux-musl.tar.gz'; RTK_SHA256='7278231dfd7e6a730a4ab7f847b195bcf02289c2d57622b0dab75a6411100c8f' ;; \
      arm64) RTK_TARBALL='rtk-aarch64-unknown-linux-gnu.tar.gz'; RTK_SHA256='c8ea4b6560841e73157c134fd4a3293914c6ede42e786ee985cf491fde691ba7' ;; \
      *) echo "Unsupported Docker target architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl --fail --silent --show-error --location \
      "https://github.com/rtk-ai/rtk/releases/download/v${RTK_VERSION}/${RTK_TARBALL}" \
      --output "/tmp/${RTK_TARBALL}"; \
    printf '%s  %s\n' "${RTK_SHA256}" "/tmp/${RTK_TARBALL}" | sha256sum --check --status; \
    mkdir -p /tmp/rtk; \
    tar --extract --gzip --file "/tmp/${RTK_TARBALL}" --directory /tmp/rtk; \
    install --mode 0755 /tmp/rtk/rtk /usr/local/bin/rtk; \
    rtk --version; \
    rm -rf /tmp/rtk "/tmp/${RTK_TARBALL}"

ENV NODE_ENV=production

# Keep the initial configuration in the image. The entrypoint seeds it into
# the persistent /opt/data volume only when that volume has no config yet.
COPY config/config.yaml /opt/data/config.yaml
COPY config/config.yaml /usr/local/share/hermes/config.yaml
COPY entrypoint.sh /usr/local/bin/hermes-entrypoint
RUN chmod 0755 /usr/local/bin/hermes-entrypoint
