#!/bin/sh
set -u

# Do not overwrite the persistent config on restart: RTK's plugin enablement
# and operator changes live in this file.
if [ ! -e /opt/data/config.yaml ]; then
  cp /usr/local/share/hermes/config.yaml /opt/data/config.yaml
fi

# Official Hermes initialization. The official plugin is installed at
# ~/.hermes/plugins/rtk-rewrite/; in this image ~/.hermes is the persistent
# /opt/data volume. Require both files from the v0.49.0 plugin layout so a
# stale marker cannot hide a missing or incomplete plugin.
export RTK_TELEMETRY_DISABLED=1
export RTK_DB_PATH=/opt/data/rtk/history.db
mkdir -p /opt/data/rtk
RTK_MARKER=/opt/data/.rtk-hermes-initialized
RTK_PLUGIN_DIR=/opt/data/plugins/rtk-rewrite
rtk_plugin_present() {
  [ -s "${RTK_PLUGIN_DIR}/__init__.py" ] && [ -s "${RTK_PLUGIN_DIR}/plugin.yaml" ]
}

if [ ! -s "${RTK_MARKER}" ] || ! rtk_plugin_present; then
  if rtk init --agent hermes; then
    if rtk_plugin_present; then
      printf '%s\n' 'rtk-hermes-initialized-v0.49.0' > "${RTK_MARKER}"
    else
      echo 'WARNING: RTK Hermes plugin initialization completed without the expected plugin files; continuing without command rewriting.' >&2
    fi
  else
    echo 'WARNING: RTK Hermes plugin initialization failed; continuing without command rewriting.' >&2
  fi
fi

exec hermes gateway run
