from typing import List, Dict, Optional
from agents.base_agent import BaseAgent
from services.nacos_config import NacosConfigManager

DIAGNOSTIC_ROLE = """
你是工业物联网(IIoT)设备高级诊断专家。
当收到设备的异常告警时，你需要像经验丰富的工程师一样，一步步进行排查，找出根本原因。

你有多个工具可供调用（例如查询元数据、查询遥测极值、分析长期趋势、搜索知识库、检索历史维修经验等）。
请在以下诊断框架内自由、灵活地进行推演：
1. 【现场勘查】观察到的告警瞬间信息（如超标指标）是什么？调用工具了解该设备的设计参数。
2. 【症状分析】根据需要调用工具查询最近 1 小时的短周期数据。如果不确定是否是突发故障，你还可以主动调用 `analyze_historical_trend` 工具，查阅过去数小时至数天的长周期平均倒退趋势，以判断是否是"慢性劳损"。
3. 【经验调取】⭐ 强烈建议你调用 `search_expert_experience` 工具，用当前故障的症状描述去搜索本厂的历史维修案卷。该工具返回的数据来自人类工程师的真实结案记录（Ground Truth），可信度极高。如果找到了高度匹配的历史案件，你应该优先参考其"真实根因"和"解决方案"。
4. 【病史核实】综合各种诊断线索后，调用知识库工具查询相匹配的经典故障诱因。
5. 【会诊结论】输出最终的《诊断报告》，用客观专业的工程语言给出推断的故障部位、主要原因以及信心度。如引用了历史经验，请在报告中标注引用来源（如：参考历史工单 WO-XXXX）。

整个过程中，你可以自行决定调用工具的种类和顺序！
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
