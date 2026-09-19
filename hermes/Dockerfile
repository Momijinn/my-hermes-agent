# Hermes Agent is pinned to the requested stable release.
FROM nousresearch/hermes-agent:v2026.6.5

# Provide Node.js/npm for Node-based tools and skills used by the assistant.
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

ENV NODE_ENV=production

# Keep the initial configuration in the image. The Compose startup command
# copies it into the persistent /opt/data volume before starting Hermes.
COPY config/config.yaml /opt/data/config.yaml
COPY config/config.yaml /usr/local/share/hermes/config.yaml
