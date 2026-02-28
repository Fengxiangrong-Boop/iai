import os
from dotenv import load_dotenv

load_dotenv()

# ================================
# Kafka Configuration
# ================================
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "192.168.0.105:9094")
KAFKA_RAW_TOPIC = "raw_sensor_data"

# ================================
# InfluxDB Configuration
# ================================
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://192.168.0.105:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "my-super-secret-auth-token")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "iai_org")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "iai")
