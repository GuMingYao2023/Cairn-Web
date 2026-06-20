#!/bin/bash
set -e

# ── Execute the command passed by Cairn Dispatcher ─────────────────────────
#  e.g. exec sleep infinity → container stays alive for agent exec commands
exec "$@"
