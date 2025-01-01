#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER crypto_user WITH PASSWORD 'Cr1pt0_2024';
    CREATE DATABASE crypto_data;
    GRANT ALL PRIVILEGES ON DATABASE crypto_data TO crypto_user;
EOSQL