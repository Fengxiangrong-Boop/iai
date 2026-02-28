from typing import List, Dict, Any, Optional
import json

class BaseAgent:
    """
    基础智能体类，封装与 LLM 的交互和 ReAct (Reasoning and Acting) 循环。
    """
    def __init__(self, name: str, role_description: str, llm_client, mcp_session=None, model_name: str = "gpt-4o"):
        self.name = name
        self.role_description = role_description
        self.llm_client = llm_client
        self.mcp_session = mcp_session
        self.model_name = model_name
        
        # 维护智能体的上下文记忆
        self.memory: List[Dict[str, Any]] = [
            {"role": "system", "content": self.role_description}
        ]
        
    def add_message(self, role: str, content: str):
        self.memory.append({"role": role, "content": content})

    async def _execute_tool(self, tool_call) -> str:
        """执行 MCP 工具并返回结果"""
        function_name = tool_call.function.name
        try:
            function_args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return f"Error: Invalid JSON arguments for {function_name}"
            
        print(f"[{self.name}] 🔧 正在调用工具 -> {function_name}({function_args})")
        
        if not self.mcp_session:
            return f"Error: MCP session is not initialized for {self.name}"

        try:
            result = await self.mcp_session.call_tool(function_name, arguments=function_args)
            raw_text = result.content[0].text
            print(f"[{self.name}] 📦 工具返回结果 -> {raw_text[:200]}...") # 打印前200字符
            return raw_text
        except Exception as e:
            error_msg = f"Error executing {function_name}: {str(e)}"
            print(f"[{self.name}] ❌ 工具执行出错 -> {error_msg}")
            return error_msg

    async def run(self, max_turns: int = 5, tools: Optional[List[Dict]] = None) -> str:
        """
        运行 ReAct 循环，直到得到最终结论或达到最大轮数。
        """
        turn = 0
        while turn < max_turns:
            print(f"\n--- [{self.name}] 思考轮次 {turn + 1}/{max_turns} ---")
            
            # 1. 询问大模型 (根据配置决定是否带工具)
            response = await self.llm_client.chat.completions.create(
                model=self.model_name,
                messages=self.memory,
                tools=tools,
                tool_choice="auto" if tools else "none"
            )
            
            response_message = response.choices[0].message
            # 将大模型的回复加入上下文
            self.memory.append(response_message)
            
            # 2. 判断大模型是否需要调用工具
            if response_message.tool_calls:
                print(f"[{self.name}] 🧠 决定执行 Action...")
                for tool_call in response_message.tool_calls:
                    # 执行工具
                    tool_result = await self._execute_tool(tool_call)
                    
                    # 将工具的反馈结果封装为 tool 消息加入上下文
                    self.memory.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": tool_result
                    })
                # 循环继续，带着工具的结果再去问大模型
                turn += 1
                continue
                
            else:
                # 3. 大模型输出了自然语言的结果，ReAct 循环结束
                print(f"[{self.name}] 🎯 思考完毕，得出最终结论。")
                return response_message.content
                
        # 达到最大轮次强制退出
        final_msg = f"[{self.name}] ⚠️ 达到最大思考轮次 ({max_turns})，强制终止推演。"
        print(final_msg)
        self.add_message("assistant", final_msg)
        return final_msg
