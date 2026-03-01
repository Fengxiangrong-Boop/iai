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


@mcp.tool()
def analyze_historical_trend(device_id: str, metric: str = "temperature", hours_back: int = 12) -> str:
    """
    分析设备在过去较长时间内（如12或24小时）的核心指标衰退趋势。
    将时序数据按小时进行降采样，并计算每小时的均值，有助于发现设备的“慢性疾病”（如缓慢升温、磨损加剧）。
    
    参数:
    - device_id: 设备的唯一标识符 (例如：PUMP_01)
    - metric: 分析指标，支持 "temperature" (温度) 或 "vibration" (震动)
    - hours_back: 分析过去多少小时的趋势，默认 12 小时
    """
    client = get_influx_client()
    try:
        device_id = device_id.upper()
        if metric not in ["temperature", "vibration"]:
            return json.dumps({"status": "error", "message": "不支持的统计指标，仅支持 temperature 或 vibration"}, ensure_ascii=False)
            
        query_api = client.query_api()
        
        # Flux 查询语法：按 1 小时为聚合窗口 (aggregateWindow)，求每小时均值
        flux_query = f'''
            from(bucket:"{INFLUXDB_BUCKET}")
            |> range(start: -{hours_back}h)
            |> filter(fn: (r) => r["_measurement"] == "sensor_raw")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["_field"] == "{metric}")
            |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
            |> yield(name: "mean")
        '''
        
        tables = query_api.query(flux_query)
        
        trend_data = []
        for table in tables:
            for record in table.records:
                time_str = record.get_time().strftime("%Y-%m-%d %H:00")
                val = record.get_value()
                if val is not None:
                    trend_data.append({"time_window": time_str, "average_value": round(val, 2)})
                    
        if not trend_data:
            return json.dumps({
                "status": "success", 
                "message": f"过去 {hours_back} 小时内无 {device_id} 的 {metric} 数据。"
            }, ensure_ascii=False)
            
        # 简单计算一下漂移量（最后一条减第一条）
        first_val = trend_data[0]["average_value"]
        last_val = trend_data[-1]["average_value"]
        drift = round(last_val - first_val, 2)
        
        summary = f"平稳"
        if drift > 0:
            summary = f"呈现上升趋势 (总增幅 {drift})"
        elif drift < 0:
            summary = f"呈现下降趋势 (总降幅 {abs(drift)})"

        return json.dumps({
            "status": "success",
            "analysis_metric": metric,
            "period": f"过去 {hours_back} 小时, 每 1 小时为统计窗口",
            "overall_trend": summary,
            "trend_data_points": trend_data
        }, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({"status": "error", "message": f"InfluxDB 趋势分析查询失败: {str(e)}"}, ensure_ascii=False)
    finally:
        client.close()


@mcp.tool()
def search_expert_experience(query: str, device_id: str = "", top_k: int = 3) -> str:
    """
    【RAG 语义检索工具】从本厂真实的历史维修案卷中，基于语义相似度搜索与当前故障最匹配的人工结案记录。
    该知识库中的数据全部来自人类工程师确认过的真实维修经验（Ground Truth），而非 AI 推测。

    使用场景：当你需要参考历史上类似故障的真实解决方案时，调用此工具。
    若检索结果为空，说明尚无类似过往记录，应基于设备手册和通用知识进行推理。

    参数:
    - query: 当前故障的症状描述 (例如："温度持续升高到85度，震动达2.1G")
    - device_id: 可选，指定设备 ID 进一步缩小搜索范围
    - top_k: 返回最相似的前 N 条记录，默认 3
    """
    try:
        from services.vector_service import search_similar, EXPERIENCE_COLLECTION

        results = search_similar(
            query_text=query,
            collection_name=EXPERIENCE_COLLECTION,
            top_k=top_k
        )

        if not results:
            return json.dumps({
                "status": "success",
                "message": "暂无与当前故障匹配的历史维修经验记录。请基于设备手册和通用工程知识进行推理。",
                "matched_cases": []
            }, ensure_ascii=False)

        # 格式化为大模型易读的结构
        cases = []
        for r in results:
            p = r["payload"]
            cases.append({
                "相似度": f"{r['score'] * 100:.1f}%",
                "工单号": p.get("order_no", "未知"),
                "设备": p.get("device_id", "未知"),
                "故障症状": p.get("symptoms", ""),
                "真实根因": p.get("root_cause", ""),
                "解决方案": p.get("solution", ""),
                "维修人": p.get("engineer", "未知"),
                "数据来源": "人工结案确认"
            })

        return json.dumps({
            "status": "success",
            "message": f"检索到 {len(cases)} 条高度相似的历史维修经验",
            "matched_cases": cases
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"RAG 检索服务异常: {str(e)}。可忽略此工具结果，基于其他信息继续推理。"
        }, ensure_ascii=False)


if __name__ == "__main__":
    # 启动时初始化向量集合
    try:
        from services.vector_service import init_collections
        init_collections()
    except Exception as e:
        print(f"⚠️ Qdrant 集合初始化跳过: {e}")

    mcp.run()
