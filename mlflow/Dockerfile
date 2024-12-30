FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /mlflow

RUN pip install mlflow psutil boto3 pymongo

RUN mkdir -p /mlflow && chmod 777 /mlflow

EXPOSE 5000

CMD mlflow server \
    --host 0.0.0.0 \
    --port 5000 \
    --backend-store-uri sqlite:////mlflow/mlflow.db \
    --default-artifact-root s3://${MLFLOW_BUCKET_NAME:-mlflow}/ \
    --serve-artifacts