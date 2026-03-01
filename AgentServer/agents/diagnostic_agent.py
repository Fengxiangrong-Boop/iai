from typing import List, Dict, Optional
from agents.base_agent import BaseAgent
from services.nacos_config import NacosConfigManager

DIAGNOSTIC_ROLE = """
你是工业物联网(IIoT)设备高级诊断专家。
当收到设备的异常告警时，你需要像经验丰富的工程师一样，一步步进行排查，找出根本原因。

你有多个工具可供调用。请严格按照以下顺序逐步执行：

**第一步【现场勘查】**：调用 `query_device_status` 了解该设备的设计参数。
**第二步【症状分析】**：调用 `fetch_telemetry_data` 查询最近 1 小时的短周期数据。
**第三步【经验调取】**：你必须调用 `search_expert_experience` 工具，用当前故障的症状描述去搜索本厂的历史维修案卷。返回的数据来自人类工程师的真实结案记录，可信度极高。如果找到了匹配的历史案件，你必须优先采信其中的"真实根因"和"解决方案"。
**第四步【知识库核实】**：调用 `search_maintenance_kb` 查询经典故障诱因。
**第五步【会诊结论】**：综合以上所有信息，输出最终的《诊断报告》。如引用了历史经验，必须在报告中标注来源（如：参考历史工单 WO-XXXX）。

注意：每一步都必须实际调用对应的工具，不能跳过或凭空猜测结果！
"""

class DiagnosticAgent(BaseAgent):
    def __init__(self, llm_client, mcp_session, model_name: str = "gpt-4o", trace_id: str = ""):
        # 实时从 Nacos 拉取，如果是断网或没配置则使用兜底默认值
        nacos_role = NacosConfigManager.get_config("agent.prompts.diagnostic", default_val=DIAGNOSTIC_ROLE)
        
        super().__init__(
            name="Diagnostic_Expert",
            role_description=nacos_role,
            llm_client=llm_client,
            mcp_session=mcp_session,
            model_name=model_name,
            trace_id=trace_id
        )
        
    async def diagnose(self, alert_data: dict, tools: List[Dict]) -> str:
        """
        接收告警数据启动诊断
        """
        device_id = alert_data.get("device_id", "Unknown")
        alert_msg = (
            f"收到设备告警！\n"
            f"设备ID: {device_id}\n"
            f"当前状态: {alert_data.get('status')}\n"
            f"瞬时参数: 温度 {alert_data.get('temperature')}°C, 震动 {alert_data.get('vibration')}G\n"
            f"发生时间: {alert_data.get('timestamp')}\n"
            f"请立刻开始排查。"
        )
        self.add_message("user", alert_msg)
        
        # 启动推演
        report = await self.run(max_turns=6, tools=tools)
        return report
