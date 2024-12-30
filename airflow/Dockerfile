FROM apache/airflow:2.8.1

USER root

# Install network utilities and dependencies
RUN apt-get update && apt-get install -y \
    iputils-ping \
    telnet \
    curl \
    build-essential \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create all necessary directories at once and set permissions
RUN mkdir -p /opt/airflow/{logs,dags,plugins,config,secrets} \
    && mkdir -p /tmp/airflow \
    && chmod -R 777 /tmp/airflow \
    && chown -R airflow:root /opt/airflow \
    && chmod -R 775 /opt/airflow \
    && chmod -R 777 /opt/airflow/logs

# Copy requirements and scripts
COPY --chown=airflow:root requirements.txt /requirements.txt
COPY --chown=airflow:root entrypoint.sh /entrypoint.sh
COPY --chown=airflow:0 wait-for-it.sh /wait-for-it.sh
RUN chmod +x /entrypoint.sh /wait-for-it.sh

# Switch to airflow user for pip install
USER airflow

# Install Python dependencies
RUN pip install --user -r /requirements.txt

# Set environment variables
ENV PYTHONPATH="/home/airflow/.local/lib/python3.8/site-packages:/opt/airflow" \
    AIRFLOW_HOME="/opt/airflow" \
    PATH="/home/airflow/.local/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE="1"

WORKDIR ${AIRFLOW_HOME}

ENTRYPOINT ["/entrypoint.sh"]
