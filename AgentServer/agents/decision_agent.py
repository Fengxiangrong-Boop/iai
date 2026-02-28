from agents.base_agent import BaseAgent

DECISION_ROLE = """
你是工厂高级维保决策专家。
你的职责是：接收来自“诊断专家”的《诊断报告》，并结合实际生产情况，制定最终的运维操作建议。
你需要输出一个包含以下内容的行动指南：
1. 故障等级评估 (P0/P1/P2)
2. 操作建议 (比如：立即停机、降级运行、或者观察等待)
3. 维修所需物料准备建议
你的报告不需要包含复杂的分析过程，只需要权威、清晰的指令性结果。
不需要调用任何外部工具，直接基于诊断专家的输入做决策。
"""

class DecisionAgent(BaseAgent):
    def __init__(self, llm_client, model_name: str = "gpt-4o"):
        # 决策智能体通常不需要自己去调 MCP 工具，它依赖上游的总结
        super().__init__(
            name="Decision_Maker",
            role_description=DECISION_ROLE,
            llm_client=llm_client,
            mcp_session=None, 
            model_name=model_name
        )
        
    async def make_decision(self, diagnostic_report: str) -> str:
        """
        根据诊断报告生成维保建议
        """
        prompt = f"以下是设备最新的《诊断报告》，请审阅并给出维保决策：\n\n{diagnostic_report}"
        self.add_message("user", prompt)
        
        # 不需要传递 tools，直接生成回答
        decision = await self.run(max_turns=3, tools=None)
        return decision
