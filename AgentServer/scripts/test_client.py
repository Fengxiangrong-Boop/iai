import os
import httpx
from dotenv import load_dotenv

load_dotenv()

async def test_api():
    base_url = "http://127.0.0.1:8000"
    
    # 模拟从 Flink 发来的告警 Payload
    flink_alert_payload = {
        "device_id": "PUMP_01",
        "status": "ANOMALY",
        "temperature": 85.2,
        "vibration": 2.8,
        "timestamp": "2026-02-27T14:30:00Z"
    }
    
    print("1. 测试系统探活...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{base_url}/api/v1/health")
            print("探活结果:", resp.json())
        except Exception as e:
            print(f"探活失败，服务可能未启动: {e}")
            return
            
    print("\n2. 测试 Flink 告警 Webhook 接入...")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base_url}/api/v1/alerts", 
            json=flink_alert_payload
        )
        print("Webhook 返回 HTTP 状态:", resp.status_code)
        print("Webhook 返回体:", resp.json())
        print("\n>> 请在 uvicorn 运行的控制台查看 AgentServer 后台输出的诊断报告和维保建议！")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_api())
