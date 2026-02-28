from typing import List, Dict, Optional
from agents.base_agent import BaseAgent
from services.nacos_config import NacosConfigManager

DIAGNOSTIC_ROLE = """
你是工业物联网(IIoT)设备诊断专家。
当收到设备的异常告警时，你需要一步步进行排查，找出根本原因。
请遵循以下 ReAct (Reasoning and Acting) 死板流程：
1. 观察到的告警信息是什么？
2. 调用工具查询该设备的设计元数据（如额定参数、安装位置）。
3. 调用时序数据工具，查询该设备最近的运行指标趋势（温度、震动等）。
4. 综合以上两点，分析当前异常是否超标，属于传感器误报还是实体故障？
5. 调用知识库工具，查询是否有类似的过往故障记录。
6. 输出最终的《诊断报告》，给出推断的故障部位和原因。
在思考过程中，请积极使用提供的工具。
报告应专业、客观。
"""

class DiagnosticAgent(BaseAgent):
    def __init__(self, llm_client, mcp_session, model_name: str = "gpt-4o"):
        # 实时从 Nacos 拉取，如果是断网或没配置则使用兜底默认值
        nacos_role = NacosConfigManager.get_config("agent.prompts.diagnostic", default_val=DIAGNOSTIC_ROLE)
        
        super().__init__(
            name="Diagnostic_Expert",
            role_description=nacos_role,
            llm_client=llm_client,
            mcp_session=mcp_session,
            model_name=model_name
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
