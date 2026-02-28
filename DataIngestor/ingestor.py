import json
import logging
from kafka import KafkaProducer
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_RAW_TOPIC, INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DataIngestor:
    """
    数据接入组件：负责将清洗后的传感器数据双写到
    1. Kafka (流处理通道)
    2. InfluxDB (时序归档通道)
    """
    def __init__(self):
        # 1. Initialize Kafka Producer
        self.producer = KafkaProducer(
            bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
            value_serializer=lambda m: json.dumps(m).encode('utf-8'),
            retries=3
        )
        
        # 2. Initialize InfluxDB Client
        self.influx_client = InfluxDBClient(
            url=INFLUXDB_URL, 
            token=INFLUXDB_TOKEN, 
            org=INFLUXDB_ORG
        )
        self.write_api = self.influx_client.write_api(write_options=SYNCHRONOUS)
        logger.info("DataIngestor initialized. Kafka and InfluxDB connected.")

    def ingest(self, payload: dict):
        """处理单条传感器数据"""
        try:
            # 1. 发送到 Kafka
            self.producer.send(KAFKA_RAW_TOPIC, payload)
            
            # 2. 写入 InfluxDB (Line Protocol)
            point = Point("sensor_raw") \
                .tag("device_id", payload["device_id"]) \
                .tag("factory_id", payload.get("factory_id", "F001")) \
                .tag("line_id", payload.get("line_id", "L003")) \
                .field("temperature", float(payload["temperature"])) \
                .field("vibration", float(payload["vibration"])) \
                .field("pressure", float(payload.get("pressure", 0.0))) \
                .field("current", float(payload.get("current", 0.0))) \
                .field("status", payload["status"])
            
            # (InfluxDB V2 Client 默认使用当前时间，如果我们指定 payload 时间也可以，这里简化)
            self.write_api.write(bucket=INFLUXDB_BUCKET, record=point)
            
            logger.debug(f"Successfully ingested data for {payload['device_id']}")
            
        except Exception as e:
            logger.error(f"Failed to ingest data: {e}")

    def close(self):
        self.producer.close()
        self.influx_client.close()
