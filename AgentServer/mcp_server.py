import json
from mcp.server.fastmcp import FastMCP
from typing import Optional

# 初始化 FastMCP 服务器
mcp = FastMCP("IIoT_Expert_Tools")

# 模拟的 MySQL 数据库 (静态元数据)
DEVICE_DB = {
    "PUMP_01": {"model": "QW-100", "location": "车间A区", "install_date": "2023-01-15", "max_temp": 65.0, "max_vibration": 1.2},
    "PUMP_02": {"model": "QW-150", "location": "车间B区", "install_date": "2022-11-20", "max_temp": 70.0, "max_vibration": 1.5},
    "PUMP_03": {"model": "QW-100", "location": "车间A区", "install_date": "2024-02-10", "max_temp": 65.0, "max_vibration": 1.2},
}

# 模拟的知识库和维修记录 (Mock)
MAINTENANCE_KB = [
    {"device_id": "PUMP_01", "date": "2023-08-10", "issue": "轴承异响，震动偏大", "action": "更换前端轴承并加注润滑油"},
    {"device_id": "PUMP_01", "date": "2024-01-05", "issue": "温度传感器漂移", "action": "重新校准 PT100 传感器"},
    {"device_id": "PUMP_02", "date": "2023-05-12", "issue": "密封圈老化漏水", "action": "更换机械密封组件"},
]

@mcp.tool()
def query_device_status(device_id: str) -> str:
    """
    根据设备 ID 查询设备的静态元数据和设计参数。
    (模拟查询 MySQL 关系型数据库)
    
    参数:
    - device_id: 设备的唯一标识符 (例如：PUMP_01)
    """
    device_id = device_id.upper()
    data = DEVICE_DB.get(device_id)
    if data:
        return json.dumps({"status": "success", "data": data}, ensure_ascii=False)
    return json.dumps({"status": "error", "message": f"未找到设备 {device_id} 的元数据。"}, ensure_ascii=False)

@mcp.tool()
def fetch_telemetry_data(device_id: str, window_mins: int = 60) -> str:
    """
    获取设备过去指定时间窗口内（默认60分钟）的关键遥测数据统计（如温度、震动的均值、峰值）。
    (模拟查询 InfluxDB 时序数据库)
    
    参数:
    - device_id: 设备的唯一标识符 (例如：PUMP_01)
    - window_mins: 往前追溯的时间窗口大小（分钟）
    """
    device_id = device_id.upper()
    if device_id not in DEVICE_DB:
        return json.dumps({"status": "error", "message": f"未找到设备 {device_id}。"}, ensure_ascii=False)
        
    # 模拟时序数据聚合结果
    mock_stats = {
        "device_id": device_id,
        "window_mins": window_mins,
        "temperature_avg": 45.3,
        "temperature_peak": 48.1,
        "vibration_avg": 0.52,
        "vibration_peak": 0.65,
        "anomaly_count": 0
    }
    
    # 为了演练效果，如果我们查 PUMP_01，我们可以捏造它刚出现过温度峰值
    if device_id == "PUMP_01":
        mock_stats["temperature_peak"] = 85.2
        mock_stats["vibration_peak"] = 2.8
        mock_stats["anomaly_count"] = 3
        
    return json.dumps({"status": "success", "data": mock_stats}, ensure_ascii=False)

@mcp.tool()
def search_maintenance_kb(device_id: str, query: Optional[str] = None) -> str:
    """
    搜索特定设备的过往维修记录和通用专家知识库。
    
    参数:
    - device_id: 设备的唯一标识符 (例如：PUMP_01)
    - query: 可选，具体的故障现象关键词查询
    """
    device_id = device_id.upper()
    records = [r for r in MAINTENANCE_KB if r["device_id"] == device_id]
    
    if query:
        records = [r for r in records if query in r["issue"] or query in r["action"]]
        
    kb_info = "通用泵类知识：若温度高于 80 度且伴随剧烈震动，极大概率为轴承严重磨损或转子不平衡，需立即停机检查。"
    
    return json.dumps({
        "status": "success",
        "maintenance_records": records,
        "expert_guidance": kb_info
    }, ensure_ascii=False)

if __name__ == "__main__":
    mcp.run()
