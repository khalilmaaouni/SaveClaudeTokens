#!/bin/sh
# fleet-join.sh: one-line MDM/Jamf deploy wrapper for `fleet.py join`.
#
# Plain POSIX sh, no bashisms (must run under dash, not just bash): no
# arrays, no [[ ]], no `function`, no `==`. Every step either succeeds or
# this script exits nonzero right there (set -eu); the final step is
# `exec`, so fleet.py's own exit code is this script's exit code, never
# swallowed or replaced.
#
# Required environment variables:
#   FLEET_STORE  git URL of the org's fleet store
#   FLEET_ORG    org name (from `fleet init`)
#   FLEET_SALT   org salt (from `fleet init`); every machine must use the
#                exact same value or machine ids stop matching across the
#                fleet
# Optional:
#   FLEET_TEAM         free team tag, for example "ios"
#   FLEET_ENVIRONMENT  free environment tag, for example "ci"
#   FLEET_PYTHON       python3 interpreter to use (default: python3)
#
# Usage (MDM/Jamf, one line):
#   FLEET_STORE=git@example.com:org/fleet-store.git FLEET_ORG=acme \
#     FLEET_SALT=change-me sh /path/to/fleet-join.sh

set -eu

: "${FLEET_STORE:?FLEET_STORE is required (git URL of the fleet store)}"
: "${FLEET_ORG:?FLEET_ORG is required (org name, from fleet init)}"
: "${FLEET_SALT:?FLEET_SALT is required (the org salt, from fleet init)}"
FLEET_PYTHON="${FLEET_PYTHON:-python3}"

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
FLEET_PY="$SCRIPT_DIR/fleet.py"

if [ ! -f "$FLEET_PY" ]; then
    echo "fleet-join.sh: fleet.py not found next to this script at $FLEET_PY" >&2
    exit 1
fi

if ! command -v "$FLEET_PYTHON" >/dev/null 2>&1; then
    echo "fleet-join.sh: $FLEET_PYTHON not found on PATH" >&2
    exit 1
fi

set -- "$FLEET_PY" join "$FLEET_STORE" --org "$FLEET_ORG" --salt "$FLEET_SALT"
if [ -n "${FLEET_TEAM:-}" ]; then
    set -- "$@" --team "$FLEET_TEAM"
fi
if [ -n "${FLEET_ENVIRONMENT:-}" ]; then
    set -- "$@" --environment "$FLEET_ENVIRONMENT"
fi

exec "$FLEET_PYTHON" "$@"
