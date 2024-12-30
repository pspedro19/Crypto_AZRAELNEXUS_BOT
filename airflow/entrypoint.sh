#!/bin/bash
set -e

# Function to initialize Airflow environment
init_airflow() {
    airflow db upgrade
    airflow users create \
        --username ${_AIRFLOW_WWW_USER_USERNAME:-admin} \
        --firstname ${_AIRFLOW_WWW_USER_FIRSTNAME:-Anonymous} \
        --lastname ${_AIRFLOW_WWW_USER_LASTNAME:-Admin} \
        --role Admin \
        --email ${_AIRFLOW_WWW_USER_EMAIL:-admin@example.org} \
        --password ${_AIRFLOW_WWW_USER_PASSWORD:-admin} \
        || true
}


# Create directories if they don't exist
directories=(
    "${AIRFLOW_HOME}/logs"
    "${AIRFLOW_HOME}/dags"
    "${AIRFLOW_HOME}/plugins"
    "${AIRFLOW_HOME}/config"
    "${AIRFLOW_HOME}/secrets"
    "${AIRFLOW_HOME}/logs/scheduler"
)

for dir in "${directories[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        chmod 777 "$dir"
    fi
done


# Create directories and set permissions

# Clean up Python cache files
find /opt/airflow -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Wait for PostgreSQL
/wait-for-it.sh postgres:5432 -t 60

umask 0002

case "$1" in
    "webserver")
        echo "Starting Airflow webserver..."
        init_airflow
        exec airflow webserver
        ;;
    "scheduler")
        echo "Starting Airflow scheduler..."
        init_airflow
        exec airflow scheduler
        ;;
    "init")
        echo "Initializing Airflow..."
        init_airflow
        exit 0
        ;;
    "version")
        exec airflow version
        ;;
    "shell"|"bash")
        exec bash
        ;;
    "python")
        exec python
        ;;
    *)
        if [ -n "$1" ]; then
            echo "Executing command: $@"
            exec "$@"
        else
            echo "No command specified. Available commands: webserver, scheduler, init, version, shell, python"
            exit 1
        fi
        ;;
esac
