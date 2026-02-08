#!/bin/sh
set -u

# Repo root is mounted at /app/autocaliweb in docker-compose.dev.yml
cd /app/autocaliweb || exit 1
echo "[dev] starting Autocaliweb via python /app/autocaliweb/cps.py (restart-on-change)"

while true; do
  python3 /app/autocaliweb/cps.py &
  pid=$!

  inotifywait -r -e modify,create,delete,move /app/autocaliweb/cps /app/autocaliweb/cps.py >/dev/null 2>&1

  echo "[dev] code change detected, restarting (pid=$pid)"
  kill "$pid" >/dev/null 2>&1 || true
  wait "$pid" >/dev/null 2>&1 || true
  sleep 0.2
done
