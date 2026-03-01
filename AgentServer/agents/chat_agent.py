"""
IAI 工程师对话智能体 (Engineer Assistant)

职责:
1. 基于用户查询，自动调用 RAG 检索知识。
2. 结合背景知识（李师傅/王工的维修经验），给出专业的口语化回答。
3. 如果不知道，则诚实告知，不胡编乱造。
"""
import logging
from typing import List, Dict, Optional
from services.rag_service import get_rag_context
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """
你是工厂的高级 AI 助手。你面前放着两部分资料：
1. 维修手册（官方规定）
2. 历史结案记录（李师傅、王工等一线大拿的真实经验）

当用户提问时，你会优先基于我们给出的【参考历史维修记录】来回答。如果记录里写了某个故障的真实原因，你就认为那是真理。

要求：
- 语气专业、实干，像个经验丰富的老师傅。
- 如果提到了历史记录，必须报出工单号 (WO-XXXX) 和维修工人的名字（如李师傅）。
- 如果参考资料里没有相关内容，请告知用户“目前经验库中尚无此类记载，建议按通用维保手册操作”。
- 禁止编造不存在的维修记录。
"""

async def run_rag_chat(llm_client, model_name: str, query: str, trace_id: str = "") -> str:
    """
    运行一次带有 RAG 增强的对话。
    """
    # 1. 自动进行语义检索
    context = await get_rag_context(query)
    
    # 2. 构建 Prompt 并调用本地大模型 (Ollama)
    full_user_msg = (
        f"用户问题: {query}\n\n"
        f"--- 以下是为你查到的关联背景知识 ---\n"
        f"{context}\n"
        f"--- 请结合以上参考资料给出回答 ---"
    )
    
    try:
        response = await llm_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": full_user_msg}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Chat RAG LLM 请求失败: {e}")
        return f"抱歉，AI 助手请求异常: {str(e)}"
