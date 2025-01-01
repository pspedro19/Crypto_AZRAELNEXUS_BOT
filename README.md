# CRYPTO AZRAEL NEXUS BOT 🤖

## System Architecture Overview

### Distributed Architecture
The system operates across two main server environments:

#### Linux Server (Primary)
- Hosts the core real-time data processing infrastructure
- Manages database and message broker systems
- Handles API and visualization services
- Coordinates all distributed services

#### Windows Server (Secondary)
- Dedicated to MyInvestor data scraping
- Runs scheduled scraping tasks at 2 AM daily
- Communicates with main system via API Gateway

### Real-time Data Infrastructure

#### Kafka Message System
```
Kafka Infrastructure:
├── Zookeeper (Management)
│   ├── Port: 2181
│   └── Configuration: ./kafka_services/zookeeper/
├── Kafka Broker
│   ├── Port: 9092 (internal), 29092 (external)
│   └── Topics:
│       ├── crypto-prices (market data)
│       ├── crypto-events (system events)
│       └── crypto-alerts (monitoring)
├── Kafka Producer Services
│   ├── Binance WebSocket Producer
│   │   └── 15-minute interval data
│   └── CoinGecko API Producer
│       └── Market data updates
└── Kafka Consumer Services
    ├── Database Writer
    ├── Alert Manager
    └── Metrics Collector
```

#### Data Flow
1. **Data Ingestion**
   - Binance WebSocket streams (real-time)
   - CoinGecko API calls (15-min intervals)
   - MyInvestor scraping (daily at 2 AM)

2. **Message Processing**
   ```mermaid
   graph LR
   A[Data Sources] --> B[Kafka Producers]
   B --> C[Kafka Broker]
   C --> D[Consumers]
   D --> E[PostgreSQL]
   E --> F[Materialized Views]
   ```

3. **Storage Layer**
   - PostgreSQL for structured data
   - MinIO for object storage
   - MongoDB for document storage

### Database Architecture

#### PostgreSQL Schema
```sql
-- Main Tables
binance_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    timestamp TIMESTAMP,
    price NUMERIC(24,8),
    volume NUMERIC(24,8)
);

coingecko_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50),
    timestamp TIMESTAMP,
    market_data JSONB
);

myinvestor_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50),
    date DATE,
    metrics JSONB
);

-- Materialized Views
crypto_combined_data (
    symbol VARCHAR(50),
    latest_price NUMERIC(24,8),
    volume_24h NUMERIC(24,8),
    market_indicators JSONB
);
```

### Service Integration

#### Inter-service Communication
```
API Gateway (Nginx)
├── FastAPI Service (:8000)
│   └── Market Data API
├── Grafana (:3000)
│   └── Dashboards
└── MLflow (:5000)
    └── Model Tracking
```

## Deployment Guide

### Linux Server Setup

1. **System Requirements**
   ```bash
   # Update system
   apt-get update && apt-get upgrade
   
   # Install dependencies
   apt-get install -y \
       docker.io \
       docker-compose \
       python3.9 \
       python3.9-venv \
       postgresql-client
   ```

2. **Docker Services**
   ```bash
   # Start core services
   docker-compose up -d postgres kafka zookeeper
   
   # Start data services
   docker-compose up -d crypto-producer crypto-consumer
   
   # Start monitoring
   docker-compose up -d grafana prometheus
   ```

3. **Environment Configuration**
   ```bash
   # Core services
   KAFKA_BOOTSTRAP_SERVERS=kafka:9092
   POSTGRES_HOST=postgres
   POSTGRES_DB=crypto_data
   
   # API Keys
   BINANCE_API_KEY=your_key
   BINANCE_API_SECRET=your_secret
   COINGECKO_API_KEY=your_key
   
   # Monitoring
   GRAFANA_ADMIN_PASSWORD=your_password
   ```

### Windows Server Setup

1. **Prerequisites**
   - Python 3.9+
   - Windows Server 2019+
   - NSSM (Non-Sucking Service Manager)

2. **Service Installation**
   ```powershell
   # Install Python dependencies
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   
   # Install Windows Service
   nssm install MyInvestorScraper python.exe
   nssm set MyInvestorScraper AppParameters "scraper.py"
   nssm set MyInvestorScraper AppDirectory "C:\Services\MyInvestor"
   ```

### Monitoring and Maintenance

#### Health Checks
```bash
# Kafka health
docker-compose exec kafka kafka-topics.sh --bootstrap-server kafka:9092 --list

# PostgreSQL health
docker-compose exec postgres pg_isready

# API health
curl http://localhost:8000/health
```

#### Backup System
```bash
# Database backup
0 0 * * * pg_dump crypto_data > /backups/db_$(date +\%Y\%m\%d).sql

# Configuration backup
0 0 * * * tar -czf /backups/config_$(date +\%Y\%m\%d).tar.gz /etc/crypto_bot/
```

#### Log Management
```
Logging Structure:
├── /var/log/crypto_bot/
│   ├── kafka/
│   │   ├── producer.log
│   │   └── consumer.log
│   ├── api/
│   │   └── api.log
│   └── scraper/
│       └── myinvestor.log
```

## Development Guidelines

### Adding New Features

1. **Kafka Topics**
   ```bash
   # Create new topic
   kafka-topics.sh --create \
       --bootstrap-server kafka:9092 \
       --topic new-feature-topic \
       --partitions 3 \
       --replication-factor 1
   ```

2. **Database Migrations**
   ```sql
   -- Create migration
   CREATE MIGRATION add_new_feature (
       -- Add new tables/columns
       ALTER TABLE crypto_data
       ADD COLUMN new_feature_column VARCHAR(50)
   );
   ```

3. **API Endpoints**
   ```python
   @app.post("/api/v1/new-feature")
   async def new_feature():
       # Implementation
       pass
   ```

### Testing Pipeline
```bash
# Unit tests
pytest tests/unit

# Integration tests
pytest tests/integration

# Performance tests
locust -f tests/performance/locustfile.py
```

## Security Considerations

### Network Security
- Internal network isolation
- API Gateway with rate limiting
- SSL/TLS encryption for all services

### Data Security
- Encrypted credentials
- Regular security audits
- Access control lists

### Monitoring Security
- Real-time threat detection
- Automated security responses
- Regular security updates

## License
Proprietary software. All rights reserved.

## Support
For technical support: support@azraelnexus.com