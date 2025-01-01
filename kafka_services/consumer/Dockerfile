FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y netcat-openbsd

COPY requirements.txt .
COPY consumer.py .
COPY entrypoint.sh .

RUN chmod +x entrypoint.sh
RUN pip install --no-cache-dir -r requirements.txt

CMD ["./entrypoint.sh"]