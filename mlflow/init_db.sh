#!/bin/bash
# Ensure the data directory exists and has the correct permissions
mkdir -p /mlflow/data
chmod 777 /mlflow/data

# Start the MLflow server
mlflow server \
    --host 0.0.0.0 \
    --port 5000 \
    --default-artifact-root ${MLFLOW_DEFAULT_ARTIFACT_ROOT} \
    --backend-store-uri ${BACKEND_STORE_URI}
