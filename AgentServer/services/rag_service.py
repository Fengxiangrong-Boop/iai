"""
IAI RAG 知识检索分发服务

职责:
1. 统一封装对 Qdrant (动态经验) 和 RAGFlow (静态手册) 的检索请求
2. 聚合多源检索结果，生成可直接喂给大模型参考的上下文 (Context)
3. 暂时只实现 Qdrant 检索，预留 RAGFlow 接口

输入: 用户的问题 (e.g. "PUMP_01 以前出过类似问题吗？")
输出: 结构化的参考背景知识字符串
"""
import logging
from typing import List, Dict, Optional
from services.vector_service import search_similar, EXPERIENCE_COLLECTION, MANUAL_COLLECTION

logger = logging.getLogger(__name__)

async def get_rag_context(query: str, top_k: int = 3) -> str:
    """
    根据用户问题，从所有可用知识源中召回最相关的上下文。
    目前包含: Qdrant 历史经验库
    未来包含: RAGFlow 手册库
    """
    context_parts = []
    
    # 1. 检索 Qdrant 动态经验库 (李师傅/王工的 Ground Truth)
    try:
        experience_results = search_similar(
            query_text=query,
            collection_name=EXPERIENCE_COLLECTION,
            top_k=top_k
        )
        
        if experience_results:
            context_parts.append("### 【参考历史维修记录 (Ground Truth)】")
            for i, res in enumerate(experience_results, 1):
                p = res["payload"]
                context_parts.append(
                    f"{i}. [相似度 {res['score']:.2f}] 工单:{p.get('order_no')} | 设备:{p.get('device_id')}\n"
                    f"   症状: {p.get('symptoms')}\n"
                    f"   结案真因: {p.get('root_cause')}\n"
                    f"   解决方案: {p.get('solution')}\n"
                    f"   技术员: {p.get('engineer')}"
                )
    except Exception as e:
        logger.error(f"RAG Qdrant 检索异常: {e}")

    # 2. (预留) 检索 RAGFlow 静态手册库
    # 这里未来会放类似 invoke_ragflow_api(query) 的代码
    context_parts.append("\n### 【参考原厂技术手册 (Static Manuals)】")
    context_parts.append("*(RAGFlow 手册引擎待接入，目前优先参考实战经验)*")

    if not context_parts:
        return "暂无相关背景知识。"
        
    return "\n\n".join(context_parts)
