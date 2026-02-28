import os
import uuid
import json
import redis
import logging
from datetime import datetime
from sqlalchemy import text
from models.database import get_db

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    redis_client.ping()
except Exception as e:
    logger.warning(f"Redis is not available: {e}. Fallback: no alert deduplication.")
    redis_client = None

class AlertService:
    @staticmethod
    def is_cooling_down(device_id: str) -> bool:
        """Check if an alert for this device is in the 5-minute cooldown period."""
        if not redis_client:
            return False # Fail-open if Redis is down
            
        key = f"alert:dedup:{device_id}"
        if redis_client.exists(key):
            return True
        
        # Set a 5-minute (300 seconds) expiration cooldown
        try:
            redis_client.setex(key, 300, "1")
        except Exception:
            pass
        return False

    @staticmethod
    def record_alert(trace_id: str, payload: dict):
        """Save raw alert mapping to MySQL."""
        db = next(get_db())
        try:
            sql = text("""
                INSERT INTO alert_log (trace_id, device_id, alert_level, alert_type, temperature, vibration, raw_payload)
                VALUES (:trace_id, :device_id, :alert_level, 'composite', :temp, :vib, :payload)
            """)
            db.execute(sql, {
                "trace_id": trace_id,
                "device_id": payload.get("device_id", "UNKNOWN"),
                "alert_level": "P1" if payload.get("temperature", 0) > 80 else "P2",
                "temp": payload.get("temperature"),
                "vib": payload.get("vibration"),
                "payload": json.dumps(payload, ensure_ascii=False)
            })
            db.commit()
            logger.info(f"✅ [MySQL] Alert {trace_id} successfully recorded in database.")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to record alert: {e}")

    @staticmethod
    def save_diagnosis(trace_id: str, device_id: str, report: str, decision: str):
        """Save AI Diagnosis and upgrade Alert status to COMPLETED."""
        db = next(get_db())
        try:
            sql = text("""
                INSERT INTO diagnosis_report (trace_id, device_id, diagnosis_text, decision_text, fault_category, severity)
                VALUES (:trace_id, :device_id, :diagnosis, :decision, 'AI预测评估', 'HIGH')
            """)
            db.execute(sql, {
                "trace_id": trace_id,
                "device_id": device_id,
                "diagnosis": report[:60000],  # Avoid overflow
                "decision": decision[:60000]
            })
            
            # Upgrade Alert Status
            sql_update = text("UPDATE alert_log SET status = 'COMPLETED' WHERE trace_id = :trace_id")
            db.execute(sql_update, {"trace_id": trace_id})
            
            db.commit()
            logger.info(f"✅ [MySQL] AI Diagnosis report for {trace_id} successfully saved.")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save AI diagnosis report: {e}")

    @staticmethod
    def create_work_order(trace_id: str, device_id: str, decision: str):
        """Automatically create a Work Order based on AI Decision."""
        db = next(get_db())
        try:
            now = datetime.now().strftime("%Y%m%d")
            order_no = f"WO-{now}-{uuid.uuid4().hex[:6].upper()}"
            sql = text("""
                INSERT INTO work_order (order_no, trace_id, device_id, order_type, priority, description, status)
                VALUES (:order_no, :trace_id, :device_id, 'EMERGENCY', 'P1', :description, 'OPEN')
            """)
            db.execute(sql, {
                "order_no": order_no,
                "trace_id": trace_id,
                "device_id": device_id,
                "description": decision[:2000] # Safe description clip
            })
            db.commit()
            logger.info(f"✅ [MySQL] Automatic Work Order {order_no} created.")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create Work Order: {e}")
