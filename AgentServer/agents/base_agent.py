from typing import List, Dict, Any, Optional
import json

class BaseAgent:
    """
    基础智能体类，封装与 LLM 的交互和 ReAct (Reasoning and Acting) 循环。
    包含错误去重机制：当同一工具连续返回相同错误时，自动注入提示引导大模型换策略。
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
            print(f"[{self.name}] 📦 工具返回结果 -> {raw_text[:200]}...")  # 打印前200字符
            return raw_text
        except Exception as e:
            error_msg = f"Error executing {function_name}: {str(e)}"
            print(f"[{self.name}] ❌ 工具执行出错 -> {error_msg}")
            return error_msg

    async def run(self, max_turns: int = 5, tools: Optional[List[Dict]] = None) -> str:
        """
        运行 ReAct 循环，直到得到最终结论或达到最大轮数。
        内置错误去重机制：连续 2 次对同一工具获得相同错误结果时，
        自动注入 system 提示，引导大模型跳过该工具直接推理。
        """
        turn = 0
        # 错误去重追踪器: {tool_name: {"last_error": str, "count": int}}
        error_tracker: Dict[str, Dict[str, Any]] = {}
        MAX_SAME_ERROR = 2  # 同一工具允许的最大连续错误次数

        while turn < max_turns:
            print(f"\n--- [{self.name}] 思考轮次 {turn + 1}/{max_turns} ---")
            
            # 1. 询问大模型 (根据配置决定是否带工具)
            kwargs = {
                "model": self.model_name,
                "messages": self.memory
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
                
            response = await self.llm_client.chat.completions.create(**kwargs)
            
            response_message = response.choices[0].message
            # 将大模型的回复加入上下文
            self.memory.append(response_message)
            
            # 2. 判断大模型是否需要调用工具
            tool_calls = response_message.tool_calls

            # 兼容：部分本地大模型偶尔会把工具 JSON 漏在 content 里面，导致未落入 tool_calls
            if not tool_calls and response_message.content:
                content_str = response_message.content.strip()
                if '{"name":' in content_str and '"arguments":' in content_str:
                    try:
                        start_idx = content_str.find("{")
                        end_idx = content_str.rfind("}") + 1
                        parsed = json.loads(content_str[start_idx:end_idx])
                        if "name" in parsed and "arguments" in parsed:
                            class DummyFunction:
                                def __init__(self, name, args):
                                    self.name = name
                                    self.arguments = json.dumps(args) if isinstance(args, dict) else args
                            class DummyToolCall:
                                def __init__(self, tid, func):
                                    self.id = tid
                                    self.function = func
                            
                            # 包装成与 OpenAI 返回一致的结构
                            tool_calls = [DummyToolCall(f"call_{turn}", DummyFunction(parsed["name"], parsed["arguments"]))]
                            print(f"[{self.name}] 🩹 触发兼容层：从普通文本提取到隐藏的工具调用 -> {parsed['name']}")
                    except Exception:
                        pass

            if tool_calls:
                print(f"[{self.name}] 🧠 决定执行 Action...")
                has_blocked_tool = False

                for tool_call in tool_calls:
                    tool_name = tool_call.function.name

                    # 检查该工具是否已经连续失败过多次
                    if tool_name in error_tracker and error_tracker[tool_name]["count"] >= MAX_SAME_ERROR:
                        blocked_msg = (
                            f"⚠️ 工具 '{tool_name}' 已连续 {error_tracker[tool_name]['count']} 次返回相同错误，"
                            f"跳过本次调用。请根据已有信息直接进行分析推理，不要再重复调用该工具。"
                        )
                        print(f"[{self.name}] 🚫 {blocked_msg}")
                        self.memory.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_name,
                            "content": blocked_msg
                        })
                        has_blocked_tool = True
                        continue

                    # 正常执行工具
                    tool_result = await self._execute_tool(tool_call)
                    
                    # 将工具的反馈结果封装为 tool 消息加入上下文
                    self.memory.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": tool_result
                    })

                    # 错误去重逻辑：检测返回内容是否包含错误标识
                    is_error = '"status": "error"' in tool_result or "Error" in tool_result[:50]
                    if is_error:
                        if tool_name in error_tracker and error_tracker[tool_name]["last_error"] == tool_result:
                            error_tracker[tool_name]["count"] += 1
                        else:
                            error_tracker[tool_name] = {"last_error": tool_result, "count": 1}
                    else:
                        # 工具成功调用，清除该工具的错误记录
                        error_tracker.pop(tool_name, None)

                # 如果所有被调用的工具都被拦截了，注入强制推理提示
                if has_blocked_tool:
                    self.add_message("system",
                        "部分工具因连续报错已被自动跳过。"
                        "请基于目前已获取的所有信息（包括告警参数本身），直接进行综合分析并输出最终结论。"
                        "不要再尝试调用已失败的工具。"
                    )

                turn += 1
                continue
                
            else:
                # 3. 大模型输出了自然语言的结果，ReAct 循环结束
                print(f"[{self.name}] 🎯 思考完毕，得出最终结论。")
                return response_message.content
                
        # 达到最大轮次强制退出
        final_msg = f"[{self.name}] ⚠️ 达到最大思考轮次 ({max_turns})，强制终止推演。"
        print(final_msg)
        # 最后再给大模型一次机会输出结论
        self.add_message("system", "你已经达到了最大工具调用轮次。请立即基于所有已获取的信息，输出你的最终分析结论。")
        try:
            final_response = await self.llm_client.chat.completions.create(
                model=self.model_name,
                messages=self.memory
            )
            return final_response.choices[0].message.content
        except Exception:
            return final_msg
