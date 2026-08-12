#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

BACKUP_ROOT=${BACKUP_ROOT:-/var/backups/adaptive-tutor}
APP_ROOT=${APP_ROOT:-/home/ubuntu/apps/knowledge-graph}
DATABASE=${DATABASE:-neo4j}
GRAPH_SERVICE=${GRAPH_SERVICE:-knowledge-graph-api.service}
TUTOR_SERVICE=${TUTOR_SERVICE:-adaptive-tutor.service}
NEO4J_SERVICE=${NEO4J_SERVICE:-neo4j.service}
RETENTION_DAYS=${RETENTION_DAYS:-14}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

BACKUP_ROOT=$(realpath -m "$BACKUP_ROOT")
case "$BACKUP_ROOT" in
  /var/backups/*|/srv/backups/*) ;;
  *) echo "BACKUP_ROOT must be below /var/backups or /srv/backups" >&2; exit 1 ;;
esac
[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || {
  echo "RETENTION_DAYS must be a non-negative integer" >&2
  exit 1
}

TARGET="$BACKUP_ROOT/$STAMP"
mkdir -p "$TARGET"
chmod 700 "$BACKUP_ROOT" "$TARGET"

graph_was_active=0
tutor_was_active=0
neo4j_was_active=0
systemctl is-active --quiet "$GRAPH_SERVICE" && graph_was_active=1 || true
systemctl is-active --quiet "$TUTOR_SERVICE" && tutor_was_active=1 || true
systemctl is-active --quiet "$NEO4J_SERVICE" && neo4j_was_active=1 || true

wait_for_neo4j() {
  for _ in $(seq 1 60); do
    curl --fail --silent http://127.0.0.1:7474/ >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

restore_services() {
  local status=${1:-0}
  if (( neo4j_was_active )); then
    systemctl start "$NEO4J_SERVICE" || status=1
    wait_for_neo4j || status=1
  fi
  if (( graph_was_active )); then systemctl start "$GRAPH_SERVICE" || status=1; fi
  if (( tutor_was_active )); then systemctl start "$TUTOR_SERVICE" || status=1; fi
  return "$status"
}

on_exit() {
  local status=$?
  trap - EXIT
  restore_services "$status"
  exit $?
}
trap on_exit EXIT

systemctl stop "$TUTOR_SERVICE" 2>/dev/null || true
if [[ -f "$APP_ROOT/data/learner.db" ]]; then
  cp --preserve=mode,timestamps "$APP_ROOT/data/learner.db" "$TARGET/learner.db"
fi
systemctl stop "$GRAPH_SERVICE" 2>/dev/null || true
systemctl stop "$NEO4J_SERVICE"

neo4j-admin database dump "$DATABASE" --to-path="$TARGET"
neo4j --version > "$TARGET/neo4j-version.txt"
find "$TARGET" -maxdepth 1 -type f ! -name SHA256SUMS -print0 \
  | xargs -0 sha256sum > "$TARGET/SHA256SUMS"
chown -R root:root "$TARGET"
chmod -R go-rwx "$TARGET"

find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d \
  -name '20??????T??????Z' -mtime "+$RETENTION_DAYS" -exec rm -rf -- {} +

trap - EXIT
restore_services 0
echo "Adaptive Tutor backup written to $TARGET"
