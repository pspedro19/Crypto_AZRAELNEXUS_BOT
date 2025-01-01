#!/bin/bash
set -e

# Esperar a que Kafka y PostgreSQL estén disponibles
while ! nc -z kafka 9092 || ! nc -z postgres 5432; do
  echo "Esperando a que los servicios estén disponibles..."
  sleep 1
done

# Iniciar el consumer
python consumer.py