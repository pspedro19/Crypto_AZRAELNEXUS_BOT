import json
import logging
import os
import time
from typing import Dict, Any
from datetime import datetime
from contextlib import contextmanager

import backoff
from kafka import KafkaConsumer
from sqlalchemy import create_engine, text, exc
from sqlalchemy.pool import QueuePool
from prometheus_client import start_http_server, Counter, Gauge, Histogram
from ratelimit import limits, sleep_and_retry
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('consumer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Prometheus metrics
MESSAGES_CONSUMED = Counter('crypto_messages_consumed_total', 'Number of messages consumed', ['source'])
CONSUMER_ERRORS = Counter('crypto_consumer_errors_total', 'Number of consumer errors', ['type'])
DB_OPERATION_TIME = Histogram('crypto_db_operation_seconds', 'Time spent on database operations', ['operation'])
PROCESSING_LAG = Gauge('crypto_processing_lag_seconds', 'Processing lag in seconds')


class CryptoDataConsumer:
    def __init__(self):
        self.setup_kafka_consumer()
        self.setup_database()
        # Start Prometheus metrics server
        start_http_server(8001)

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=5,
        max_time=300
    )
    def setup_kafka_consumer(self) -> None:
        """Initialize Kafka consumer with retries and optimized settings"""
        try:
            self.consumer = KafkaConsumer(
                'crypto-prices',
                bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092').split(','),
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id='crypto_data_group',
                consumer_timeout_ms=60000,
                session_timeout_ms=30000,
                max_poll_interval_ms=300000,
                max_poll_records=500,
                fetch_max_bytes=52428800,  # 50MB
                fetch_max_wait_ms=500,
                security_protocol='PLAINTEXT'  # Change to 'SSL' for production
            )
            logger.info("Kafka consumer initialized successfully")
        except Exception as e:
            CONSUMER_ERRORS.labels(type='initialization').inc()
            logger.error(f"Failed to initialize Kafka consumer: {e}")
            raise

    def setup_database(self) -> None:
        """Setup database connection pool with retries"""
        try:
            db_url = f"postgresql://{os.getenv('POSTGRES_USER')}:" \
                     f"{os.getenv('POSTGRES_PASSWORD')}@" \
                     f"{os.getenv('POSTGRES_HOST')}:5432/" \
                     f"{os.getenv('POSTGRES_DB')}"
            
            self.engine = create_engine(
                db_url,
                poolclass=QueuePool,
                pool_size=10,
                max_overflow=20,
                pool_timeout=30,
                pool_pre_ping=True
            )
            
            # Test connection
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection pool established successfully")
        except Exception as e:
            CONSUMER_ERRORS.labels(type='database_init').inc()
            logger.error(f"Failed to setup database connection: {e}")
            raise

    @contextmanager
    def get_db_connection(self):
        """Database connection context manager with error handling"""
        connection = None
        try:
            connection = self.engine.connect()
            yield connection
        except exc.SQLAlchemyError as e:
            CONSUMER_ERRORS.labels(type='database_connection').inc()
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if connection:
                connection.close()

    @sleep_and_retry
    @limits(calls=100, period=1)  # Rate limit to 100 operations per second
    def store_binance_data(self, data: Dict[str, Any]) -> None:
        """Store Binance data with rate limiting and monitoring"""
        query = """
        INSERT INTO binance_data (
            symbol, timestamp, open, high, low, close, volume, trades
        ) VALUES (
            :symbol, to_timestamp(:timestamp/1000), :open, :high, :low, :close, :volume, :trades
        )
        ON CONFLICT (symbol, timestamp) 
        DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            trades = EXCLUDED.trades
        """
        start_time = time.time()
        try:
            with self.get_db_connection() as conn:
                conn.execute(text(query), data)
                conn.commit()
                MESSAGES_CONSUMED.labels(source='binance').inc()
                logger.debug(f"Stored Binance data for {data['symbol']}")
        except Exception as e:
            CONSUMER_ERRORS.labels(type='binance_store').inc()
            logger.error(f"Error storing Binance data: {e}")
            raise
        finally:
            DB_OPERATION_TIME.labels(operation='binance_store').observe(time.time() - start_time)

    @sleep_and_retry
    @limits(calls=100, period=1)  # Rate limit to 100 operations per second
    def store_coingecko_data(self, data: Dict[str, Any]) -> None:
        """Store CoinGecko data with rate limiting and monitoring"""
        query = """
        INSERT INTO coingecko_data (
            symbol, timestamp, price_usd, market_cap, volume_24h, price_change_24h
        ) VALUES (
            :symbol,
            to_timestamp(:timestamp/1000),
            :price_usd,
            :market_cap,
            :volume_24h,
            :price_change_24h
        )
        ON CONFLICT (symbol, timestamp) 
        DO UPDATE SET
            price_usd = EXCLUDED.price_usd,
            market_cap = EXCLUDED.market_cap,
            volume_24h = EXCLUDED.volume_24h,
            price_change_24h = EXCLUDED.price_change_24h
        """
        start_time = time.time()
        try:
            with self.get_db_connection() as conn:
                conn.execute(text(query), data)
                conn.commit()
                MESSAGES_CONSUMED.labels(source='coingecko').inc()
                logger.debug(f"Stored CoinGecko data for {data['symbol']}")
        except Exception as e:
            CONSUMER_ERRORS.labels(type='coingecko_store').inc()
            logger.error(f"Error storing CoinGecko data: {e}")
            raise
        finally:
            DB_OPERATION_TIME.labels(operation='coingecko_store').observe(time.time() - start_time)

    def refresh_materialized_view(self) -> None:
        """Refresh materialized view with monitoring"""
        start_time = time.time()
        try:
            with self.get_db_connection() as conn:
                conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY crypto_combined_data"))
                conn.commit()
                logger.info("Refreshed materialized view")
        except Exception as e:
            CONSUMER_ERRORS.labels(type='view_refresh').inc()
            logger.error(f"Error refreshing materialized view: {e}")
            raise
        finally:
            DB_OPERATION_TIME.labels(operation='view_refresh').observe(time.time() - start_time)

    def process_message(self, message: Dict[str, Any]) -> None:
        """Process incoming Kafka message with monitoring"""
        try:
            source = message.get('source')
            current_time = time.time()
            message_time = message.get('timestamp', 0) / 1000  # Convert to seconds
            PROCESSING_LAG.set(current_time - message_time)

            if source == 'binance':
                self.store_binance_data(message)
            elif source == 'coingecko':
                self.store_coingecko_data(message)
                # Refresh materialized view after CoinGecko data updates
                self.refresh_materialized_view()
            else:
                logger.warning(f"Unknown data source: {source}")
                CONSUMER_ERRORS.labels(type='unknown_source').inc()
        except Exception as e:
            CONSUMER_ERRORS.labels(type='message_processing').inc()
            logger.error(f"Error processing message: {e}")

    def start(self) -> None:
        """Start the consumer service with monitoring"""
        logger.info("Starting Crypto Data Consumer")
        last_refresh = time.time()
        refresh_interval = 900  # 15 minutes in seconds
        message_count = 0
        batch_size = 100

        while True:
            try:
                message_batch = self.consumer.poll(timeout_ms=1000, max_records=batch_size)
                
                for topic_partition, messages in message_batch.items():
                    for message in messages:
                        self.process_message(message.value)
                        message_count += 1

                        # Commit offsets every batch_size messages
                        if message_count >= batch_size:
                            self.consumer.commit()
                            message_count = 0

                # Check if we need to refresh the materialized view
                current_time = time.time()
                if current_time - last_refresh >= refresh_interval:
                    self.refresh_materialized_view()
                    last_refresh = current_time

            except Exception as e:
                CONSUMER_ERRORS.labels(type='consumer_loop').inc()
                logger.error(f"Error in consumer loop: {e}")
                time.sleep(5)  # Wait before retrying

    def cleanup(self) -> None:
        """Cleanup resources safely"""
        try:
            if hasattr(self, 'consumer'):
                self.consumer.close()
            if hasattr(self, 'engine'):
                self.engine.dispose()
            logger.info("Cleaned up resources")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


def main():
    """Main entry point with error handling"""
    consumer = None
    try:
        consumer = CryptoDataConsumer()
        consumer.start()
    except KeyboardInterrupt:
        logger.info("Shutting down consumer gracefully")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        if consumer:
            consumer.cleanup()


if __name__ == "__main__":
    main()