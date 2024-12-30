#!/bin/bash
# init-secondary.sh

#!/bin/bash

echo "Iniciando configuración del servidor secundario..."

# Variables de entorno
MONGO_HOST="mongo-secondary"
MONGO_PORT="27017"
PRIMARY_IP="10.116.0.4"
SECONDARY_IP="10.116.0.2"
REPLICA_SET="rs0"

# Esperar a que MongoDB local esté disponible
echo "Esperando a que MongoDB local esté disponible..."
until mongosh --host $MONGO_HOST --port $MONGO_PORT --eval 'db.adminCommand("ping")' >/dev/null 2>&1; do
    echo "Esperando a MongoDB local..."
    sleep 5
done

echo "MongoDB local está disponible."

# Esperar a que el primario esté disponible
echo "Esperando a que el servidor primario esté disponible..."
until mongosh --host $PRIMARY_IP --port $MONGO_PORT --eval 'db.adminCommand("ping")' >/dev/null 2>&1; do
    echo "Esperando al servidor primario..."
    sleep 5
done

echo "Servidor primario está disponible."


# Verificar conexión con el primario
echo "Verificando conexión con el primario..."
if mongosh --host $PRIMARY_IP --eval "db.adminCommand('ping')" >/dev/null 2>&1; then
    echo "Conexión con primario establecida"
    
    # Intentar agregar este nodo al replica set
    echo "Intentando agregar nodo al replica set..."
    mongosh --host $PRIMARY_IP --eval "
    rs.add('$SECONDARY_IP:27017');" || {
        echo "Error al agregar nodo al replica set"
        exit 1
    }
    
    echo "Nodo agregado exitosamente"
else
    echo "No se puede conectar al servidor primario"
    exit 1
fi

# Mantener el contenedor corriendo
tail -f /dev/null
