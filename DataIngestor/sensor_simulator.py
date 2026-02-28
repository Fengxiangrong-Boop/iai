import time
import random
import logging
from datetime import datetime, timezone
from ingestor import DataIngestor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEVICES = [
    {"device_id": "PUMP_01", "base_temp": 45.0, "base_vib": 0.50},
    {"device_id": "PUMP_02", "base_temp": 50.0, "base_vib": 0.60},
    {"device_id": "PUMP_03", "base_temp": 40.0, "base_vib": 0.40},
]

def simulate_data():
    """持续生成传感器模拟数据并双写输入流"""
    
    ingestor = DataIngestor()
    logger.info("Starting Sensor Simulator...")
    
    # 模拟异常触发器的计数器
    anomalies_triggered = 0
    
    try:
        while True:
            for device in DEVICES:
                # 随机生成一些基础抖动数据
                temp_fluctuation = random.uniform(-2.0, 2.0)
                vib_fluctuation = random.uniform(-0.1, 0.1)
                
                temp = device["base_temp"] + temp_fluctuation
                vib = device["base_vib"] + vib_fluctuation
                
                status = "NORMAL"
                
                # 每隔一定的概率 (或者故意造点异常) 让 PUMP_01 飞温
                if device["device_id"] == "PUMP_01" and random.random() < 0.05 and anomalies_triggered < 3:
                    temp = 85.5 + random.uniform(0, 5)  # 超过阈值 (65)
                    vib = 2.8 + random.uniform(0, 0.5)    # 超过阈值 (1.2)
                    status = "ANOMALY"
                    anomalies_triggered += 1
                    logger.warning(f"🚨 触发模拟异常信号: PUMP_01 (Temp: {temp:.2f}, Vib: {vib:.2f})")
                
                payload = {
                    "device_id": device["device_id"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "temperature": round(temp, 2),
                    "vibration": round(vib, 3),
                    "pressure": round(random.uniform(1.8, 2.5), 1),
                    "current": round(random.uniform(14.0, 16.5), 1),
                    "status": status,
                    "factory_id": "F001",
                    "line_id": "L003"
                }
                
                # 数据接入双写
                ingestor.ingest(payload)
                
            # 每 2 秒生成一次数据
            time.sleep(2)
            
    except KeyboardInterrupt:
        logger.info("Simulator terminated by user.")
    finally:
        ingestor.close()

if __name__ == "__main__":
    simulate_data()
