#!/bin/sh
# ------------------------------------------------------------------ #
# Sauvegarde automatique quotidienne de la base PostgreSQL Bovo.
#
# Ce script tourne dans le conteneur ``bovo-backup`` et effectue :
#   1. Un pg_dump complet (format compressé gzip -9)
#   2. Une rotation des archives (14 dernières conservées)
#   3. Un log stdout lisible dans ``docker logs bovo-backup``
#
# Le script est écrit en /bin/sh pur (compatible Alpine Postgres).
# Il boucle indéfiniment avec un sleep de 24h entre chaque backup.
# ------------------------------------------------------------------ #

set -eu

DB_HOST="${DB_HOST:-db}"
DB_USER="${POSTGRES_USER:-bovo}"
DB_NAME="${POSTGRES_DB:-bovo}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_COUNT="${KEEP_COUNT:-14}"
SLEEP_SECONDS="${SLEEP_SECONDS:-86400}"

mkdir -p "$BACKUP_DIR"

echo "[backup] Service démarré (host=$DB_HOST db=$DB_NAME user=$DB_USER)."
echo "[backup] Conservation : ${KEEP_COUNT} archives. Intervalle : ${SLEEP_SECONDS}s."

while true; do
    DAY=$(date +%F)
    OUTFILE="$BACKUP_DIR/bovo-$DAY.sql.gz"
    echo "[backup] $DAY: pg_dump en cours…"
    if pg_dump -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" | gzip -9 > "$OUTFILE.tmp"; then
        mv "$OUTFILE.tmp" "$OUTFILE"
        SIZE=$(du -h "$OUTFILE" | cut -f1)
        echo "[backup] $DAY OK ($SIZE) → $OUTFILE"
    else
        echo "[backup] $DAY ERREUR — pg_dump a échoué."
        rm -f "$OUTFILE.tmp"
    fi

    # Rotation : ne conserver que les KEEP_COUNT plus récents.
    ls -1t "$BACKUP_DIR"/bovo-*.sql.gz 2>/dev/null \
        | tail -n +$((KEEP_COUNT + 1)) \
        | while read -r old; do
            echo "[backup] Rotation : suppression $old"
            rm -f -- "$old"
        done

    echo "[backup] Prochain backup dans ${SLEEP_SECONDS}s."
    sleep "$SLEEP_SECONDS"
done
