#!/bin/sh
set -eu

PI_AGENT_SOURCE_DIR="${PI_AGENT_SOURCE_DIR:-/pi/agent-source}"
PI_WEB_SEARCH_CONFIG_SOURCE="${PI_WEB_SEARCH_CONFIG_SOURCE:-/pi/web-search.json}"
PI_CODING_AGENT_DIR="${PI_CODING_AGENT_DIR:-/tmp/pi-agent}"

umask 077
rm -rf "$PI_CODING_AGENT_DIR"
mkdir -p "$PI_CODING_AGENT_DIR"

if [ -d "$PI_AGENT_SOURCE_DIR" ]; then
    cp -R "$PI_AGENT_SOURCE_DIR"/. "$PI_CODING_AGENT_DIR"/
fi
if [ -f "$PI_WEB_SEARCH_CONFIG_SOURCE" ]; then
    cp "$PI_WEB_SEARCH_CONFIG_SOURCE" "$PI_CODING_AGENT_DIR/web-search.json"
fi

export PI_CODING_AGENT_DIR
exec /opt/research-venv/bin/python -m scripts.research_loop "$@"
