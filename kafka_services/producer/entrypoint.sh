#!/bin/bash
set -e

# Esperar a que Kafka esté disponible
while ! nc -z kafka 9092; do
  echo "Esperando a que Kafka esté disponible..."
  sleep 1
done

# Iniciar el producer
python producer.py