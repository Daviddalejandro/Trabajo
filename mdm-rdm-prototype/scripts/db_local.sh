#!/usr/bin/env bash
# Alternativa sin Docker (SPEC §4): clúster PostgreSQL 16 local con initdb/pg_ctl.
# Uso: scripts/db_local.sh start|stop|status|reset
set -euo pipefail
PGBIN="${PGBIN:-/usr/lib/postgresql/16/bin}"
PORT="${PGPORT_LOCAL:-5433}"
PGUSER_LOCAL="${PGUSER_LOCAL:-mdm}"
DB="${PGDB_LOCAL:-mdm_prototype}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${PGDATA_LOCAL:-$ROOT/.pgdata}"

run_as() { # PostgreSQL no corre como root: delega a un usuario sin privilegios si hace falta
  if [ "$(id -u)" = "0" ]; then
    id "$PGUSER_LOCAL" >/dev/null 2>&1 || useradd -m -s /bin/bash "$PGUSER_LOCAL"
    mkdir -p "$DATA"; chown -R "$PGUSER_LOCAL" "$DATA"
    runuser -u "$PGUSER_LOCAL" -- "$@"
  else
    "$@"
  fi
}

case "${1:-start}" in
  start)
    if [ ! -f "$DATA/PG_VERSION" ]; then
      mkdir -p "$DATA"
      run_as "$PGBIN/initdb" -D "$DATA" -U "$PGUSER_LOCAL" --auth=trust -E UTF8 --locale=C.UTF-8 >/dev/null
    fi
    run_as "$PGBIN/pg_ctl" -D "$DATA" -l "$DATA/pg.log" \
      -o "-p $PORT -c listen_addresses=127.0.0.1 -c unix_socket_directories=/tmp" start >/dev/null
    for i in $(seq 1 20); do "$PGBIN/pg_isready" -h 127.0.0.1 -p "$PORT" -q && break; sleep 0.5; done
    psql -h 127.0.0.1 -p "$PORT" -U "$PGUSER_LOCAL" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB'" | grep -q 1 \
      || psql -h 127.0.0.1 -p "$PORT" -U "$PGUSER_LOCAL" -d postgres -qc "CREATE DATABASE $DB"
    echo "PostgreSQL local listo: postgresql+psycopg://$PGUSER_LOCAL@127.0.0.1:$PORT/$DB"
    ;;
  stop)   run_as "$PGBIN/pg_ctl" -D "$DATA" stop -m fast >/dev/null && echo "detenido" ;;
  status) "$PGBIN/pg_isready" -h 127.0.0.1 -p "$PORT" ;;
  reset)  "$0" stop || true; rm -rf "$DATA"; "$0" start ;;
  *) echo "uso: $0 start|stop|status|reset"; exit 2 ;;
esac
