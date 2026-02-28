import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from influxdb_client import InfluxDBClient
from dotenv import load_dotenv

load_dotenv()

# ================================
# MySQL Configuration (SQLAlchemy)
# ================================
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "root")
MYSQL_HOST = os.getenv("MYSQL_HOST", "192.168.0.105")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_DB = os.getenv("MYSQL_DB", "iai")

# quote_plus 对密码中的特殊字符（如 @）进行 URL 编码，防止连接串解析错误
# charset=utf8mb4 确保中文字段正确编码传输，防止出现乱码
SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{quote_plus(MYSQL_PASSWORD)}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ================================
# InfluxDB Configuration
# ================================
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://192.168.0.105:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "my-super-secret-auth-token")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "iai_org")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "iai")

def get_influx_client():
    return InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
