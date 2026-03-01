"""
IAI RAG 向量服务核心模块

职责:
1. 管理 Qdrant 向量数据库连接与集合初始化
2. 使用大模型 API 进行文本嵌入 (Embedding)
3. 提供向量化写入与语义检索的统一接口

输入/输出示例:
  - 输入: "温度85度，震动2.1G，轴承磨损"
  - 输出: [{"score": 0.92, "text": "...", "source": "WO-2025-001", ...}, ...]

非确定性边界:
  - Embedding 模型的输出受模型版本和输入文本影响
  - 检索结果的相似度分数存在浮点精度差异
"""
import os
import logging
import hashlib
from typing import List, Dict, Optional
from datetime import datetime

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue
)
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ================================
# 配置常量
# ================================
QDRANT_HOST = os.getenv("QDRANT_HOST", "192.168.0.105")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

# Embedding 配置 - 使用与主 LLM 相同的 API 提供商
EMBEDDING_API_KEY = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "embedding-3")

# 向量维度 (智谱 embedding-3 / OpenAI text-embedding-3-small 均为 2048 或 1024)
VECTOR_DIM = int(os.getenv("VECTOR_DIM", "2048"))

# 集合名称
EXPERIENCE_COLLECTION = "experiences"  # 动态经验集合（人工结案工单）
MANUAL_COLLECTION = "manuals"          # 静态手册集合（PDF 等文档）

# ================================
# 初始化 Qdrant 客户端
# ================================
_qdrant_client: Optional[QdrantClient] = None
_embedding_client: Optional[OpenAI] = None


def get_qdrant_client() -> Optional[QdrantClient]:
    """获取 Qdrant 客户端单例"""
    global _qdrant_client
    if _qdrant_client is None:
        try:
            _qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=10)
            _qdrant_client.get_collections()
            logger.info(f"✅ Qdrant 向量数据库连接成功 ({QDRANT_HOST}:{QDRANT_PORT})")
        except Exception as e:
            logger.warning(f"⚠️ Qdrant 连接失败: {e}，RAG 功能将不可用")
            _qdrant_client = None
    return _qdrant_client


def get_embedding_client() -> Optional[OpenAI]:
    """获取 Embedding 客户端单例"""
    global _embedding_client
    if _embedding_client is None:
        try:
            _embedding_client = OpenAI(
                api_key=EMBEDDING_API_KEY,
                base_url=EMBEDDING_BASE_URL
            )
            logger.info("✅ Embedding 客户端初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ Embedding 客户端初始化失败: {e}")
            _embedding_client = None
    return _embedding_client


def init_collections():
    """初始化 Qdrant 集合（如果不存在则创建）"""
    client = get_qdrant_client()
    if not client:
        return

    for collection_name in [EXPERIENCE_COLLECTION, MANUAL_COLLECTION]:
        try:
            existing = [c.name for c in client.get_collections().collections]
            if collection_name not in existing:
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=VECTOR_DIM,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"✅ Qdrant 集合 '{collection_name}' 创建成功 (维度={VECTOR_DIM})")
            else:
                logger.info(f"✅ Qdrant 集合 '{collection_name}' 已存在")
        except Exception as e:
            logger.error(f"❌ 创建集合 '{collection_name}' 失败: {e}")


# ================================
# Embedding 核心函数
# ================================
def embed_text(text: str) -> Optional[List[float]]:
    """
    将文本转化为密集向量

    输入: "轴承磨损导致高温"
    输出: [0.012, -0.345, ..., 0.789] (维度=VECTOR_DIM)
    """
    client = get_embedding_client()
    if not client:
        logger.warning("Embedding 客户端不可用")
        return None

    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        vector = response.data[0].embedding

        # 自动检测并适配向量维度
        global VECTOR_DIM
        if len(vector) != VECTOR_DIM:
            logger.warning(f"⚠️ 检测到向量维度 {len(vector)} 与配置 {VECTOR_DIM} 不同，自动适配")
            VECTOR_DIM = len(vector)

        return vector
    except Exception as e:
        logger.error(f"❌ Embedding 失败: {e}")
        return None


# ================================
# 写入操作
# ================================
def _text_hash(text: str) -> str:
    """生成文本的唯一哈希 ID，防止重复写入"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def ingest_experience(
    device_id: str,
    symptoms: str,
    root_cause: str,
    solution: str,
    order_no: str,
    engineer: str = "未知"
) -> bool:
    """
    将人工结案的真实维修经验写入 Qdrant 经验集合

    输入示例:
      device_id: "PUMP_01"
      symptoms: "温度85度，震动2.1G"
      root_cause: "传感器线路松动"
      solution: "紧固接口并重新校准"
      order_no: "WO-20260301-A1B2C3"
      engineer: "张师傅"

    输出: True/False 表示写入是否成功
    """
    client = get_qdrant_client()
    if not client:
        return False

    # 拼接为结构化文本用于向量化
    full_text = (
        f"设备: {device_id}\n"
        f"故障症状: {symptoms}\n"
        f"真实根因: {root_cause}\n"
        f"解决方案: {solution}\n"
        f"维修人: {engineer}"
    )

    vector = embed_text(full_text)
    if not vector:
        return False

    point_id = _text_hash(f"{order_no}_{device_id}")
    try:
        client.upsert(
            collection_name=EXPERIENCE_COLLECTION,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "device_id": device_id,
                        "symptoms": symptoms,
                        "root_cause": root_cause,
                        "solution": solution,
                        "order_no": order_no,
                        "engineer": engineer,
                        "source": "human_verified",
                        "ingested_at": datetime.now().isoformat()
                    }
                )
            ]
        )
        logger.info(f"✅ [RAG] 经验入库成功: {order_no} ({device_id})")
        return True
    except Exception as e:
        logger.error(f"❌ [RAG] 经验入库失败: {e}")
        return False


def ingest_manual_chunk(
    chunk_text: str,
    source_file: str,
    page_number: int = 0,
    device_type: str = "general"
) -> bool:
    """
    将手册或文档的文本块写入 Qdrant 手册集合

    输入示例:
      chunk_text: "当泵体温度超过70度时，应立即检查冷却水回路..."
      source_file: "西门子QW-100维修手册.pdf"
      page_number: 42
      device_type: "pump"

    输出: True/False 表示写入是否成功
    """
    client = get_qdrant_client()
    if not client:
        return False

    vector = embed_text(chunk_text)
    if not vector:
        return False

    point_id = _text_hash(f"{source_file}_p{page_number}_{chunk_text[:50]}")
    try:
        client.upsert(
            collection_name=MANUAL_COLLECTION,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "text": chunk_text,
                        "source_file": source_file,
                        "page_number": page_number,
                        "device_type": device_type,
                        "source": "manual",
                        "ingested_at": datetime.now().isoformat()
                    }
                )
            ]
        )
        return True
    except Exception as e:
        logger.error(f"❌ [RAG] 手册块入库失败: {e}")
        return False


# ================================
# 检索操作
# ================================
def search_similar(
    query_text: str,
    collection_name: str = EXPERIENCE_COLLECTION,
    top_k: int = 3,
    device_type_filter: Optional[str] = None
) -> List[Dict]:
    """
    语义相似度检索：在指定集合中找出与查询文本最相似的 Top-K 条记录

    输入示例:
      query_text: "水泵温度异常升高，伴有震动"
      collection_name: "experiences"
      top_k: 3

    输出示例:
      [
        {"score": 0.94, "payload": {"root_cause": "...", "solution": "...", ...}},
        {"score": 0.87, "payload": {...}},
      ]
    """
    client = get_qdrant_client()
    if not client:
        return []

    query_vector = embed_text(query_text)
    if not query_vector:
        return []

    try:
        # 构建可选的过滤条件
        search_filter = None
        if device_type_filter:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="device_type",
                        match=MatchValue(value=device_type_filter)
                    )
                ]
            )

        results = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=search_filter
        )

        return [
            {
                "score": round(hit.score, 4),
                "payload": hit.payload
            }
            for hit in results.points
        ]
    except Exception as e:
        logger.error(f"❌ [RAG] 向量检索失败: {e}")
        return []
