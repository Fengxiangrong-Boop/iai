"""
IAI 工单结案 API 路由

工程师在现场维修完成后，通过此接口提交真实的维修结果。
系统会将人工确认的真实经验自动向量化，写入 Qdrant 经验库。

接口:
- PUT /api/v1/workorder/{order_no}/complete  → 工程师结案并录入真实维修记录
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session
from models.database import get_db
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class WorkOrderCompleteRequest(BaseModel):
    """工程师结案提交的表单"""
    root_cause: str = Field(..., description="真实根因 (例如：'周边有取暖器导致传感器受热干扰')")
    solution: str = Field(..., description="实际采取的解决措施 (例如：'移走取暖器，传感器恢复正常')")
    engineer: str = Field(default="未指定", description="维修工程师姓名")
    actual_hours: Optional[float] = Field(default=None, description="实际工时")
    notes: Optional[str] = Field(default=None, description="补充备注")


@router.put("/api/v1/workorder/{order_no}/complete")
def complete_work_order(order_no: str, req: WorkOrderCompleteRequest, db: Session = Depends(get_db)):
    """
    工程师结案接口 (Human-in-the-Loop 闭环节点)

    当工程师在现场完成维修后，调用此接口提交真实的维修记录。
    系统会自动将这份经过人工验证的"真相"向量化，存入 Qdrant 经验库，
    让下一次 AI 诊断时能够引用这条来自一线的真实经验。
    """
    try:
        # 1. 查询工单是否存在
        row = db.execute(text(
            "SELECT order_no, device_id, trace_id, description, status "
            "FROM work_order WHERE order_no = :order_no LIMIT 1"
        ), {"order_no": order_no}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"工单 {order_no} 不存在")

        order_data = dict(row._mapping)

        if order_data["status"] == "COMPLETED":
            raise HTTPException(status_code=400, detail=f"工单 {order_no} 已结案，不能重复提交")

        # 2. 更新工单状态为 COMPLETED
        update_sql = text("""
            UPDATE work_order 
            SET status = 'COMPLETED', 
                completed_at = NOW(),
                actual_hours = :actual_hours
            WHERE order_no = :order_no
        """)
        db.execute(update_sql, {
            "order_no": order_no,
            "actual_hours": req.actual_hours
        })
        db.commit()
        logger.info(f"✅ 工单 {order_no} 已由 {req.engineer} 结案")

        # 3. 🔥 核心：将人工确认的真实经验写入 Qdrant 向量库（飞轮启动！）
        rag_result = "跳过"
        try:
            from services.vector_service import ingest_experience

            # 从工单的 AI 描述中获取症状信息
            ai_description = order_data.get("description", "")
            # 获取告警时的参数作为症状补充
            alert_row = db.execute(text(
                "SELECT temperature, vibration FROM alert_log WHERE trace_id = :trace_id LIMIT 1"
            ), {"trace_id": order_data.get("trace_id", "")}).fetchone()

            symptoms = f"AI 初步描述: {ai_description[:200]}"
            if alert_row:
                alert_data = dict(alert_row._mapping)
                symptoms = (
                    f"温度: {alert_data.get('temperature', '?')}°C, "
                    f"震动: {alert_data.get('vibration', '?')}G. "
                    f"AI 初步描述: {ai_description[:150]}"
                )

            success = ingest_experience(
                device_id=order_data["device_id"],
                symptoms=symptoms,
                root_cause=req.root_cause,
                solution=req.solution,
                order_no=order_no,
                engineer=req.engineer
            )
            rag_result = "成功" if success else "失败"
        except Exception as e:
            logger.warning(f"⚠️ RAG 入库异常（不影响结案）: {e}")
            rag_result = f"异常: {e}"

        return {
            "status": "success",
            "message": f"工单 {order_no} 结案成功",
            "rag_ingestion": rag_result,
            "detail": {
                "order_no": order_no,
                "device_id": order_data["device_id"],
                "engineer": req.engineer,
                "root_cause": req.root_cause,
                "solution": req.solution
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ 工单结案失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
