#!/bin/bash
set -e

# Verificar si MongoDB está respondiendo
mongosh --quiet --eval 'db.runCommand("ping").ok' &>/dev/null || exit 1

# Verificar conectividad con el primario
if [ ! -z "$MONGO_PRIMARY_IP" ]; then
    nc -z -w5 $MONGO_PRIMARY_IP ${MONGO_PORT:-27017} || exit 1
fi

# Verificar estado del replica set
RS_STATUS=$(mongosh --quiet --eval '
try {
    rs.status().ok || rs.status().code === 94;
} catch(err) {
    if(err.codeName === "NotYetInitialized") {
        true;
    } else {
        false;
    }
}
') || exit 1

exit 0