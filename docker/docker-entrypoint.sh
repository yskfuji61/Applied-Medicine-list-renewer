#!/bin/sh
set -eu

if [ "${1:-}" = "pharmalist" ]; then
  shift
fi

mkdir -p "${PHARMALIST_AUDIT_ROOT:-/data/audit}"

exec pharmalist "$@"