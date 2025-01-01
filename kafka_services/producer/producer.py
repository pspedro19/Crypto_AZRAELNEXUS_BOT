import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional

import schedule
import backoff
from binance import ThreadedWebsocketManager
from kafka import KafkaProducer
from pycoingecko import CoinGeckoAPI
from prometheus_client import start_http_server, Counter, Gauge
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('producer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Prometheus metrics
MESSAGES_PRODUCED = Counter('crypto_messages_produced_total', 'Number of messages produced', ['source'])
PRODUCER_ERRORS = Counter('crypto_producer_errors_total', 'Number of producer errors', ['type'])
PROCESSING_TIME = Gauge('crypto_processing_time_seconds', 'Time taken to process message', ['source'])

class CryptoDataProducer:
    def __init__(self):
        self.setup_kafka_producer()
        # self.setup_binance_client()  # Comentado ya que no usaremos Binance activamente
        self.setup_coingecko_client()
        self.symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ALGOUSDT']
        self.coin_ids = {
            'BTCUSDT': 'bitcoin',
            'ETHUSDT': 'ethereum',
            'SOLUSDT': 'solana',
            'ALGOUSDT': 'algorand'
        }
        # Start Prometheus metrics server
        start_http_server(8000)

    def setup_kafka_producer(self) -> None:
        """Initialize Kafka producer with optimized settings"""
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092').split(','),
                value_serializer=lambda x: json.dumps(x).encode('utf-8'),
                retries=5,
                acks='all',
                batch_size=16384,  # Optimize throughput
                linger_ms=100,     # Allow batching
                compression_type='gzip',  # Compress messages
                request_timeout_ms=30000,
                max_block_ms=60000,
                buffer_memory=67108864,  # 64MB buffer
                security_protocol='PLAINTEXT'  # Change to 'SSL' for production
            )
            logger.info("Kafka producer initialized successfully")
        except Exception as e:
            PRODUCER_ERRORS.labels(type='initialization').inc()
            logger.error(f"Error initializing Kafka producer: {e}")
            raise

    def setup_binance_client(self) -> None:
        """Initialize Binance websocket client with retry mechanism"""
        try:
            self.binance_api_key = os.getenv('BINANCE_API_KEY')
            self.binance_api_secret = os.getenv('BINANCE_API_SECRET')
            self.twm = ThreadedWebsocketManager(
                api_key=self.binance_api_key,
                api_secret=self.binance_api_secret,
                tld='com'
            )
            logger.info("Binance client initialized successfully")
        except Exception as e:
            PRODUCER_ERRORS.labels(type='binance_init').inc()
            logger.error(f"Error initializing Binance client: {e}")
            raise

    def setup_coingecko_client(self) -> None:
        """Initialize CoinGecko client with API key"""
        try:
            self.cg = CoinGeckoAPI()
            # Set API key if available
            api_key = os.getenv('COINGECKO_API_KEY')
            if api_key:
                self.cg.api_key = api_key
            logger.info("CoinGecko client initialized successfully")
        except Exception as e:
            PRODUCER_ERRORS.labels(type='coingecko_init').inc()
            logger.error(f"Error initializing CoinGecko client: {e}")
            raise

    def handle_binance_message(self, msg: Dict[str, Any]) -> None:
        """Process incoming Binance websocket messages with metrics"""
        start_time = time.time()
        try:
            if msg.get('e') == 'kline':
                data = {
                    'source': 'binance',
                    'symbol': msg['s'],
                    'timestamp': msg['E'],
                    'open': float(msg['k']['o']),
                    'high': float(msg['k']['h']),
                    'low': float(msg['k']['l']),
                    'close': float(msg['k']['c']),
                    'volume': float(msg['k']['v']),
                    'trades': msg['k']['n'],
                    'closed': msg['k']['x']
                }
                self.send_to_kafka('crypto-prices', data)
                MESSAGES_PRODUCED.labels(source='binance').inc()
                logger.debug(f"Processed Binance data for {msg['s']}")
        except Exception as e:
            PRODUCER_ERRORS.labels(type='binance_processing').inc()
            logger.error(f"Error processing Binance message: {e}")
        finally:
            PROCESSING_TIME.labels(source='binance').set(time.time() - start_time)

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
        max_time=30
    )
    def fetch_coingecko_data(self) -> None:
        """Fetch data from CoinGecko API with exponential backoff"""
        start_time = time.time()
        try:
            for symbol, coin_id in self.coin_ids.items():
                data = self.cg.get_coin_by_id(
                    coin_id,
                    localization=False,
                    tickers=False,
                    market_data=True,
                    community_data=False,
                    developer_data=False,
                    sparkline=False
                )
                
                processed_data = {
                    'source': 'coingecko',
                    'symbol': symbol,
                    'timestamp': int(datetime.now().timestamp() * 1000),
                    'price_usd': data['market_data']['current_price']['usd'],
                    'market_cap': data['market_data']['market_cap']['usd'],
                    'volume_24h': data['market_data']['total_volume']['usd'],
                    'price_change_24h': data['market_data']['price_change_percentage_24h'],
                    'last_updated': data['last_updated']
                }
                
                self.send_to_kafka('crypto-prices', processed_data)
                MESSAGES_PRODUCED.labels(source='coingecko').inc()
                logger.info(f"Fetched CoinGecko data for {symbol}")
                
                # Rate limiting to avoid API restrictions
                time.sleep(1.5)
                
        except Exception as e:
            PRODUCER_ERRORS.labels(type='coingecko_fetch').inc()
            logger.error(f"Error fetching CoinGecko data: {e}")
            raise
        finally:
            PROCESSING_TIME.labels(source='coingecko').set(time.time() - start_time)

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
        max_time=10
    )
    def send_to_kafka(self, topic: str, data: Dict[str, Any]) -> None:
        """Send data to Kafka with retries and monitoring"""
        try:
            future = self.producer.send(topic, value=data)
            future.get(timeout=10)  # Wait for the send to complete
            logger.debug(f"Sent data to Kafka topic {topic}")
        except Exception as e:
            PRODUCER_ERRORS.labels(type='kafka_send').inc()
            logger.error(f"Error sending to Kafka: {e}")
            raise

    def start(self) -> None:
        """Start the producer service with error handling"""
        try:
            logger.info("Starting Crypto Data Producer")
            
            # Commented out Binance-related code
            # self.twm.start()
            
            # Start all symbol streams
            # for symbol in self.symbols:
            #     self.twm.start_kline_socket(
            #         callback=self.handle_binance_message,
            #         symbol=symbol,
            #         interval='15m'
            #     )
            
            # Schedule CoinGecko data fetch every 15 minutes
            schedule.every(15).minutes.do(self.fetch_coingecko_data)
            
            # Initial fetch
            self.fetch_coingecko_data()
            
            # Keep the script running
            while True:
                schedule.run_pending()
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Fatal error in producer service: {e}")
            raise
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Cleanup resources safely"""
        try:
            # self.twm.stop()  # Comentado ya que no estamos usando Binance
            if hasattr(self, 'producer'):
                self.producer.flush(timeout=10)
                self.producer.close(timeout=10)
            logger.info("Cleaned up resources")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

def main():
    """Main entry point with error handling"""
    producer = None
    try:
        producer = CryptoDataProducer()
        producer.start()
    except KeyboardInterrupt:
        logger.info("Shutting down producer gracefully")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        if producer:
            producer.cleanup()

if __name__ == "__main__":
    main()