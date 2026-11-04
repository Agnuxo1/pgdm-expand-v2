#!/bin/bash
# Starts PostgreSQL and sshd with random TEST credentials (they only live inside the
# container and are never printed) and runs the requested command.
set -euo pipefail
export PGDATA=/pgdata/data
mkdir -p /pgdata /results
chown postgres:postgres /pgdata
# One container per data volume: kernel lock on a file inside the volume, held for the container lifetime.
exec 8>/pgdata/.container.lock
flock -w 7200 8 || { echo "data volume busy"; exit 75; }
PG_PASS=$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)
SSH_PASS=$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  su postgres -c "initdb -D $PGDATA -U postgres --auth-local=trust --auth-host=scram-sha-256 >/dev/null"
fi
# Server configuration: common base + experiment profile (PG_PROFILE).
cp /work/bench/pg_base.conf "$PGDATA/bench_base.conf"
: > "$PGDATA/bench_profile.conf"
if [ -n "${PG_PROFILE:-}" ] && [ -f "/work/bench/profiles/${PG_PROFILE}.conf" ]; then
  cp "/work/bench/profiles/${PG_PROFILE}.conf" "$PGDATA/bench_profile.conf"
fi
grep -q "include 'bench_base.conf'" "$PGDATA/postgresql.conf" || {
  echo "include 'bench_base.conf'" >> "$PGDATA/postgresql.conf"
  echo "include 'bench_profile.conf'" >> "$PGDATA/postgresql.conf"
}
su postgres -c "pg_ctl -D $PGDATA -l /pgdata/server.log -w start >/dev/null"
psql -U postgres -qAt -c "DO \$\$BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='pdm') THEN CREATE ROLE pdm LOGIN CREATEDB; END IF; END\$\$;"
psql -U postgres -qAt -c "ALTER ROLE pdm PASSWORD '$PG_PASS';" >/dev/null
echo "pdm:$SSH_PASS" | chpasswd 2>/dev/null
# The Manager runs psql on the server with PGPASSWORD; ~/.pgpass of the SSH user covers it too.
echo "localhost:5432:*:pdm:$PG_PASS" > /home/pdm/.pgpass
echo "127.0.0.1:5432:*:pdm:$PG_PASS" >> /home/pdm/.pgpass
chown pdm:pdm /home/pdm/.pgpass; chmod 600 /home/pdm/.pgpass
/usr/sbin/sshd
export BENCH_PG_PASS="$PG_PASS" BENCH_SSH_PASS="$SSH_PASS" PG_KAGGLE_CHALLENGE_PASS="$PG_PASS"
export PYTHONDONTWRITEBYTECODE=1
cd /work
set +e
"$@"
rc=$?
set -e
su postgres -c "pg_ctl -D $PGDATA -m fast -w stop >/dev/null" || true
exit $rc
