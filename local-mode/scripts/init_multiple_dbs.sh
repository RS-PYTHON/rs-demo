#!/bin/bash
set -e

if [ -z "$POSTGRES_PI_DB" ]; then
    echo "ERROR: POSTGRES_PI_DB environment variable is not set!"
    exit 1
fi

echo "Creating extra database: $POSTGRES_PI_DB"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE "$POSTGRES_PI_DB";
EOSQL
