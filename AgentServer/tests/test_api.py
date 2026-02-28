from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from api import app, state

client = TestClient(app)

def test_health_check_unhealthy():
    # 测试在 MCP 没有连接时的按预期返回 unhealthy
    state.mcp_session = None
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["mcp_connection"] == "unhealthy"

def test_health_check_healthy():
    # 测试在 MCP 连接后的状态
    state.mcp_session = object() # Mock object
    state.tools_cache = [{"name": "mock_tool"}]
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["mcp_connection"] == "healthy"
    assert response.json()["tools_loaded"] == 1

@patch("api.OPENAI_API_KEY", "mocked_key")
def test_receive_alert():
    # 测试 webhook endpoint
    payload = {
        "device_id": "PUMP_01",
        "status": "ANOMALY",
        "temperature": 85.2,
        "vibration": 2.8,
        "timestamp": "2026-02-27T14:30:00Z"
    }
    
    response = client.post("/api/v1/alerts", json=payload)
    assert response.status_code == 200
    assert "trace_id" in response.json()
    assert "告警已接收" in response.json()["message"]
