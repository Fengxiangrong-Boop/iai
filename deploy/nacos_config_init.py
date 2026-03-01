import os
import json
import logging
import urllib.request
import urllib.parse

logging.basicConfig(level=logging.INFO, format='%(message)s')

NACOS_URL = os.getenv("NACOS_URL", "http://127.0.0.1:8848")
NAMESPACE_ID = "" # Default public namespace

def publish_config(data_id, group, content, content_type="text"):
    url = f"{NACOS_URL}/nacos/v1/cs/configs"
    data = {
        "tenant": NAMESPACE_ID,
        "dataId": data_id,
        "group": group,
        "content": content,
        "type": content_type
    }
    encoded_data = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded_data)
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            status_code = response.getcode()
            response_text = response.read().decode("utf-8")
            if status_code == 200 and response_text == "true":
                logging.info(f"✅ 成功发布配置: {data_id} [{group}]")
                return True
            else:
                logging.error(f"❌ 失败发布配置: {data_id} - HTTP {status_code}: {response_text}")
                return False
    except Exception as e:
        logging.error(f"⚠️ 请求 Nacos 失败: {e}")
        return False

def init_nacos_configs():
    # 1. 动态阈值配置 (JSON格式)
    thresholds = {
        "temperature_anomaly_threshold": 65.0,
        "vibration_anomaly_threshold": 1.2,
        "pump_01_anomaly_prob": 0.05
    }
    publish_config("sensor.thresholds.json", "DEFAULT_GROUP", json.dumps(thresholds, indent=2, ensure_ascii=False), "json")

    # 2. 诊断专家 Prompt (文本格式)
    diagnostic_prompt = """你是工业物联网(IIoT)设备诊断专家。
当收到设备的异常告警时，你需要一步步进行排查，找出根本原因。
请遵循以下 ReAct (Reasoning and Acting) 死板流程：
1. 观察到的告警信息是什么？
2. 调用工具查询该设备的设计元数据（如额定参数、安装位置）。
3. 调用时序数据工具，查询该设备最近的运行指标趋势（温度、震动等）。
4. 综合以上两点，分析当前异常是否超标，属于传感器误报还是实体故障？
5. 调用知识库工具，查询是否有类似的过往故障记录。
6. 输出最终的《诊断报告》，给出推断的故障部位和原因。
在思考过程中，请积极使用提供的工具。
报告应专业、客观。"""
    publish_config("agent.prompts.diagnostic", "DEFAULT_GROUP", diagnostic_prompt)

    # 3. 决策专家 Prompt (文本格式)
    decision_prompt = """你是工业智能体决策中心专家。
你将收到设备诊断专家出具的《诊断报告》和告警相关的原始数据。
请根据这些信息，生成一份简明扼要的《运维工单建议》。
1. 提取诊断报告中最核心的故障点。
2. 给出维修建议（例如：更换部件、加注润滑油、清理灰尘等）。
3. 如果需要，请分点列出。
无需多写废话，内容必须是可以直接给到一线维修工人的指令。"""
    publish_config("agent.prompts.decision", "DEFAULT_GROUP", decision_prompt)
    
    logging.info("🎉 Nacos 配置初始化完毕！你可以前往 http://192.168.0.105:8848/nacos 查看。")

if __name__ == "__main__":
    init_nacos_configs()
