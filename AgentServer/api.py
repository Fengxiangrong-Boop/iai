import os
import sys
import uuid
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from openai import AsyncOpenAI

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from logger import logger, get_logger_with_trace
from agents.diagnostic_agent import DiagnosticAgent
from agents.decision_agent import DecisionAgent
from services.alert_service import AlertService
from services.nacos_registry import register_to_nacos, deregister_from_nacos, start_heartbeat, stop_heartbeat

# === 初始化环境与客户端 ===
# 加载 .env 文件
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o")

# 初始化真实的 LLM 客户端
llm_client = AsyncOpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL
)

# 存储全局的 MCP ClientSession 和工具缓存
class AppState:
    mcp_session: Optional[ClientSession] = None
    tools_cache: List[Dict[str, Any]] = []

state = AppState()

# === 帮助函数：将 MCP Schema 转为 OpenAI Tools Schema ===
def mcp_tools_to_openai_tools(mcp_tools) -> List[Dict[str, Any]]:
    openai_tools = []
    for tool in mcp_tools:
        schema = tool.inputSchema
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": schema
            }
        })
    return openai_tools

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 生命周期管理
    在此处启动并连接到 MCP Server (mcp_server.py)，并获取工具列表
    """
    logger.info("🚀 正在启动 Agent Server 生命周期...")
    from contextlib import AsyncExitStack
    
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["mcp_server.py"]
    )
    
    async with AsyncExitStack() as stack:
        try:
            stdio_transport = await stack.enter_async_context(stdio_client(server_params))
            read, write = stdio_transport
            
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            
            state.mcp_session = session
            logger.info("✅ 本地 MCP Server (技能库) 连接并初始化完成！")
            
            # 拉取完整的工具栈并缓存为 OpenAI 格式
            tools_response = await session.list_tools()
            state.tools_cache = mcp_tools_to_openai_tools(tools_response.tools)
            logger.info(f"✅ 成功加载工具: {[t.name for t in tools_response.tools]}")
            
            # [Phase E] Nacos 服务注册
            register_to_nacos()
            start_heartbeat()
            
            yield
            
        except Exception as e:
            logger.error(f"❌ 启动 MCP Client 失败: {e}", exc_info=True)
            raise e
        finally:
            stop_heartbeat()
            deregister_from_nacos()
            logger.info("🛑 正在关闭服务和释放资源...")

app = FastAPI(
    title="IIoT Expert Agent API",
    description="工业物联网设备诊断多智能体系统",
    version="1.0.0",
    lifespan=lifespan
)

# === 注册 Web 管理后台路由 ===
from routes.dashboard import router as dashboard_router
app.include_router(dashboard_router)

# === 数据模型定义 ===
class AlertPayload(BaseModel):
    device_id: str = Field(..., description="设备唯一标识符")
    status: str = Field(..., description="设备状态 (如 NORMAL, ANOMALY)")
    temperature: float = Field(..., description="实时温度")
    vibration: float = Field(..., description="实时震动")
    timestamp: str = Field(..., description="告警发生时间")

class ChatRequest(BaseModel):
    query: str = Field(..., description="用户的提问内容")
    session_id: Optional[str] = Field(default=None, description="对话 Session 标识")

class DiagnosisResponse(BaseModel):
    trace_id: str
    message: str

class ChatResponse(BaseModel):
    trace_id: str
    answer: str

# === 多智能体协同作战入口 (Agent Router) ===
async def process_alert_task(trace_id: str, alert_data: dict):
    """
    背景任务：接收到告警后的多智能体工作流。
    """
    req_logger = get_logger_with_trace(trace_id)
    device_id = alert_data.get("device_id", "UNKNOWN")
    
    # [Phase 2] 0. 告警去重判断 (Redis 5分钟冷却窗)
    if AlertService.is_cooling_down(device_id):
        req_logger.warning(f"❄️ 设备 {device_id} 在5分钟冷却期内，本次重复告警被过滤。")
        return
        
    # [Phase 2] 0.5 记录告警入库
    req_logger.info(f"📍 开始处理设备告警, Data: {alert_data}")
    AlertService.record_alert(trace_id, alert_data)
    
    try:
        # 1. 启动诊断专家
        req_logger.info("👨‍⚕️ [步骤 1] 启动诊断专家 (Diagnostic Expert)...")
        from services.event_bus import event_bus
        event_bus.publish("global_stream", f"<b>[{trace_id[:8]}]</b> 👨‍⚕️ 启动诊断专家对 {device_id} 进行排查...")
        diagnostic_agent = DiagnosticAgent(
            llm_client=llm_client, 
            mcp_session=state.mcp_session, 
            model_name=MODEL_NAME,
            trace_id=trace_id
        )
        report = await diagnostic_agent.diagnose(alert_data, tools=state.tools_cache)
        req_logger.info(f"📄 诊断报告出炉:\n{report}")
        event_bus.publish("global_stream", f"<b>[{trace_id[:8]}]</b> 📄 诊断报告已生成")
        
        # 2. 启动决策专家
        req_logger.info("👨‍⚖️ [步骤 2] 启动决策专家 (Decision Maker)...")
        event_bus.publish("global_stream", f"<b>[{trace_id[:8]}]</b> 👨‍⚖️ 启动决策专家正在制定方案...")
        decision_agent = DecisionAgent(
            llm_client=llm_client,
            model_name=MODEL_NAME,
            trace_id=trace_id
        )
        decision = await decision_agent.make_decision(diagnostic_report=report)
        req_logger.info(f"📜 最终维保决策:\n{decision}")
        
        # [Phase 2] 3. 诊断报告和工单自动入库落盘 (闭环)
        req_logger.info("💾 [步骤 3] 正在落盘诊断报告与工单记录...")
        AlertService.save_diagnosis(trace_id, device_id, report, decision)
        AlertService.create_work_order(trace_id, device_id, decision)
        
        req_logger.info("✅ 告警智能诊断流转处理和工单入库闭环全部完成！")
        event_bus.publish("global_stream", f"<b>[{trace_id[:8]}]</b> ✅ 流转闭环完成，诊断报告与工单已落盘！")
        
    except Exception as e:
        req_logger.error(f"❌ 处理流转异常: {e}", exc_info=True)
        from services.event_bus import event_bus
        event_bus.publish("global_stream", f"<b>[{trace_id[:8]}]</b> ❌ 智能体系统异常: {e}")

# === API 路由定义 ===

@app.post("/api/v1/alerts", response_model=DiagnosisResponse, summary="接收实时告警")
async def receive_alert(payload: AlertPayload, background_tasks: BackgroundTasks):
    """
    接收来自实时系统 (如 Flink) 的设备异常告警Webhook。
    接收后立即返回 ACK，并在后台启动智能诊断工作流。
    """
    trace_id = uuid.uuid4().hex
    req_logger = get_logger_with_trace(trace_id)
    
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="未配置大模型 API KEY")
        
    req_logger.info(f"📥 接收到告警 payload: {payload.model_dump()}")
    
    # 将处理过程放入后台任务，快速响应 Flink (避免超时)
    background_tasks.add_task(process_alert_task, trace_id, payload.model_dump())
    
    return DiagnosisResponse(
        trace_id=trace_id,
        message="告警已接收，诊断组已受命入场调查。"
    )

@app.post("/api/v1/chat", response_model=ChatResponse, summary="终端聊天入口")
async def chat_endpoint(request: ChatRequest):
    """
    预留的人机交互接口，可以实现自由提问等能力。
    （注：目前简单起见，单智能体直接回复，如果需要同样支持调用工具，可以单独实例化一个 Agent）
    """
    trace_id = uuid.uuid4().hex
    req_logger = get_logger_with_trace(trace_id)
    req_logger.info(f"💬 收到聊天请求: {request.query}")
    
    # 临时启动一个通用询问，暂不调用完整流转
    try:
        response = await llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "你是工厂的AI助手。"},
                {"role": "user", "content": request.query}
            ]
        )
        answer = response.choices[0].message.content
        return ChatResponse(trace_id=trace_id, answer=answer)
    except Exception as e:
        req_logger.error(f"LLM 请求失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/health", summary="健康探针")
async def health_check():
    mcp_status = "healthy" if state.mcp_session is not None else "unhealthy"
    return {
        "status": "ok", 
        "mcp_connection": mcp_status, 
        "model": MODEL_NAME,
        "tools_loaded": len(state.tools_cache)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
