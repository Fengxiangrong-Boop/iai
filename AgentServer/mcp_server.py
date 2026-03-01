import json
from mcp.server.fastmcp import FastMCP
from typing import Optional

from sqlalchemy import text
from models.database import get_db, SessionLocal, get_influx_client, INFLUXDB_BUCKET

# 初始化 FastMCP 服务器
mcp = FastMCP("IIoT_Expert_Tools")

@mcp.tool()
def query_device_status(device_id: str) -> str:
    """
    根据设备 ID 查询设备的静态元数据和设计参数。
    (真实查询 MySQL 关系型数据库)
    
    参数:
    - device_id: 设备的唯一标识符 (例如：PUMP_01)
    """
    db = SessionLocal()
    try:
        device_id = device_id.upper()
        query = text("SELECT * FROM device_registry WHERE device_id = :device_id")
        result = db.execute(query, {"device_id": device_id}).fetchone()
        
        if result:
            data = dict(result._mapping)
            for key, val in data.items():
                if hasattr(val, "isoformat"):
                    data[key] = val.isoformat()
                elif hasattr(val, "normalize"): # 处理 Decimal 类型
                    data[key] = float(val)
            return json.dumps({"status": "success", "data": data}, ensure_ascii=False)
        return json.dumps({"status": "error", "message": f"未找到设备 {device_id} 的元数据。"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
    finally:
        db.close()

@mcp.tool()
def fetch_telemetry_data(device_id: str, window_mins: int = 60) -> str:
    """
    获取设备过去指定时间窗口内（默认60分钟）的关键遥测数据统计（如温度、震动的均值、峰值）。
    (真实查询 InfluxDB 时序数据库)
    
    参数:
    - device_id: 设备的唯一标识符 (例如：PUMP_01)
    - window_mins: 往前追溯的时间窗口大小（分钟）
    """
    client = get_influx_client()
    try:
        device_id = device_id.upper()
        query_api = client.query_api()
        
        # 实时聚合查询 InfluxDB
        flux_query = f'''
            from(bucket:"{INFLUXDB_BUCKET}")
            |> range(start: -{window_mins}m)
            |> filter(fn: (r) => r["_measurement"] == "sensor_raw")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["_field"] == "temperature" or r["_field"] == "vibration")
            |> yield(name: "raw")
        '''
        tables = query_api.query(flux_query)
        
        temp_vals = []
        vib_vals = []
        for table in tables:
            for record in table.records:
                if record.get_field() == "temperature":
                    temp_vals.append(record.get_value())
                elif record.get_field() == "vibration":
                    vib_vals.append(record.get_value())
                    
        if not temp_vals and not vib_vals:
            return json.dumps({
                "status": "success", 
                "message": f"所选时间段内尚未生成设备 {device_id} 的真实遥测数据，等待采集层输入。", 
                "data": {"temperature_avg": 0, "temperature_peak": 0, "vibration_avg": 0, "vibration_peak": 0}
            }, ensure_ascii=False)
            
        mock_stats = {
            "device_id": device_id,
            "window_mins": window_mins,
            "temperature_avg": round(sum(temp_vals)/len(temp_vals), 2),
            "temperature_peak": round(max(temp_vals), 2),
            "vibration_avg": round(sum(vib_vals)/len(vib_vals), 3),
            "vibration_peak": round(max(vib_vals), 3),
            "anomaly_count": 0 
        }
        return json.dumps({"status": "success", "data": mock_stats}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": f"InfluxDB 查询失败: {str(e)}"}, ensure_ascii=False)
    finally:
        client.close()

@mcp.tool()
def search_maintenance_kb(device_id: str, query_str: Optional[str] = None) -> str:
    """
    搜索特定设备的通用专家知识库。
    
    参数:
    - device_id: 设备的唯一标识符 (例如：PUMP_01)
    - query_str: 可选，具体的故障现象关键词查询
    """
    db = SessionLocal()
    try:
        device_id = device_id.upper()
        # 查询设备类型用于过滤知识库
        query_type = text("SELECT device_type FROM device_registry WHERE device_id = :device_id")
        type_res = db.execute(query_type, {"device_id": device_id}).fetchone()
        
        device_type = "pump"
        if type_res:
            device_type = type_res._mapping['device_type']
            
        # 模糊匹配搜索
        if query_str:
            sql = """
                SELECT fault_pattern, symptoms, root_cause, solution, prevention 
                FROM maintenance_kb 
                WHERE device_type = :device_type 
                AND (fault_pattern LIKE :query OR symptoms LIKE :query OR root_cause LIKE :query)
            """
            kb_res = db.execute(text(sql), {"device_type": device_type, "query": f"%{query_str}%"}).fetchall()
        else:
            sql = "SELECT fault_pattern, symptoms, root_cause, solution, prevention FROM maintenance_kb WHERE device_type = :device_type"
            kb_res = db.execute(text(sql), {"device_type": device_type}).fetchall()
            
        records = [dict(r._mapping) for r in kb_res]
        
        # 过滤日期类型确保 JSON 序列化
        for rec in records:
            for k, v in rec.items():
                if hasattr(v, "isoformat"): rec[k] = v.isoformat()
                
        return json.dumps({
            "status": "success",
            "device_type": device_type,
            "expert_guidance": records,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": f"MySQL 查询失败: {str(e)}"}, ensure_ascii=False)
    finally:
        db.close()

if __name__ == "__main__":
    mcp.run()
