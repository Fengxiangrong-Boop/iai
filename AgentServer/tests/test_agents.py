import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from agents.base_agent import BaseAgent
from agents.diagnostic_agent import DiagnosticAgent
from agents.decision_agent import DecisionAgent

@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    # Mock chat completion response
    mock_response = MagicMock()
    mock_message = MagicMock()
    mock_message.content = "这是一份模拟的最终结论报告。"
    mock_message.tool_calls = None
    mock_response.choices = [MagicMock(message=mock_message)]
    
    client.chat.completions.create = AsyncMock(return_value=mock_response)
    return client

@pytest.fixture
def mock_mcp_session():
    session = AsyncMock()
    
    # Mock tool call result
    mock_result = MagicMock()
    mock_text = MagicMock(text=json.dumps({"status": "success", "data": "mocked_data"}))
    mock_result.content = [mock_text]
    
    session.call_tool = AsyncMock(return_value=mock_result)
    return session

@pytest.mark.asyncio
async def test_base_agent_run(mock_llm_client, mock_mcp_session):
    agent = BaseAgent(
        name="TestAgent",
        role_description="You are a test agent.",
        llm_client=mock_llm_client,
        mcp_session=mock_mcp_session
    )
    
    agent.add_message("user", "Hello!")
    result = await agent.run(max_turns=1)
    
    assert "模拟的最终结论报告" in result
    mock_llm_client.chat.completions.create.assert_called_once()

@pytest.mark.asyncio
async def test_diagnostic_agent(mock_llm_client, mock_mcp_session):
    agent = DiagnosticAgent(
        llm_client=mock_llm_client,
        mcp_session=mock_mcp_session
    )
    
    alert_data = {
        "device_id": "PUMP_01",
        "status": "ANOMALY",
        "temperature": 85.0,
        "vibration": 2.0,
        "timestamp": "2026-02-27T12:00:00Z"
    }
    
    report = await agent.diagnose(alert_data, tools=[])
    assert report is not None
    assert "专家" in agent.role_description

@pytest.mark.asyncio
async def test_decision_agent(mock_llm_client):
    agent = DecisionAgent(
        llm_client=mock_llm_client
    )
    
    decision = await agent.make_decision("设备轴承损坏，建议更换。")
    assert decision is not None
    assert "决策专家" in agent.role_description or "专家" in agent.role_description
    assert agent.mcp_session is None
