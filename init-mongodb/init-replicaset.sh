#!/bin/bash
# init-secondary.sh

echo "Iniciando configuración del servidor secundario..."

# Variables de entorno
MONGO_HOST="mongo-secondary"  # Nombre del contenedor local
MONGO_PORT="27017"
PRIMARY_IP="64.227.24.227"
SECONDARY_IP="143.198.115.114"
REPLICA_SET="rs0"

# Función para esperar a que MongoDB esté disponible
wait_for_mongo() {
    local host=$1
    echo "Esperando a que MongoDB en $host esté disponible..."
    until mongosh --host $host --port $MONGO_PORT --quiet --eval 'db.runCommand("ping").ok' > /dev/null 2>&1; do
        echo "Esperando conexión a MongoDB en $host..."
        sleep 5
    done
}

# Esperar a que el MongoDB local esté disponible
wait_for_mongo $MONGO_HOST

# Esperar a que el primario esté disponible
wait_for_mongo $PRIMARY_IP

echo "MongoDB primario y secundario están disponibles."
echo "Intentando agregar este nodo al replica set..."

# Esperar un poco más para asegurarnos que el primario está completamente configurado
sleep 10

# Intentar agregar este nodo al replica set
mongosh --host $PRIMARY_IP --port $MONGO_PORT --eval "
rs.add({
    _id: 1,
    host: '$SECONDARY_IP:$MONGO_PORT',
    priority: 1
});"

echo "Esperando a que el nodo se sincronice..."
while true; do
    STATE=$(mongosh --host $MONGO_HOST --port $MONGO_PORT --quiet --eval "rs.status().myState" || echo "0")
    if [ "$STATE" == "2" ]; then
        echo "Nodo configurado como SECONDARY exitosamente"
        break
    fi
    echo "Esperando a que el nodo se convierta en SECONDARY... Estado actual: $STATE"
    sleep 5
done

echo "Configuración del secundario completada"

# Mantener el contenedor corriendo
tail -f /dev/null