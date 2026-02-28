# 🏭 IAI - 工业智能体系统 (Industrial AI Intelligence)

> **AI 驱动的工业物联网实时设备诊断与智能运维平台**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Flink](https://img.shields.io/badge/Flink-2.2.0-orange.svg)](https://flink.apache.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 📖 项目简介

IAI 是一套面向工业物联网场景的**端到端实时智能体系统**，实现了从传感器数据采集、实时流计算、AI 智能诊断到自动工单生成的全链路闭环。

### ✨ 核心能力

- 🔄 **实时数据采集** — 传感器数据双写 Kafka + InfluxDB
- ⚡ **Flink 流计算** — 异常实时检测 + 分钟级指标聚合
- 🧠 **AI 智能诊断** — 大模型 (GLM-4) + MCP 工具链 + ReAct 推理
- 🔧 **自动工单闭环** — 告警去重 → 诊断 → 决策 → 工单自动生成
- 📊 **Grafana 实时大屏** — 温度/震动趋势、告警记录、工单状态

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Grafana 可视化大屏                        │
│         (温度趋势 / 震动趋势 / 告警表 / 工单表)                 │
└───────────────────┬───────────────────┬─────────────────────┘
                    │                   │
              ┌─────▼─────┐       ┌─────▼─────┐
              │  InfluxDB  │       │   MySQL   │
              │ (时序数据)  │       │ (告警/工单) │
              └─────▲─────┘       └─────▲─────┘
                    │                   │
    ┌───────────────┼───────────────────┼──────────────┐
    │               │                   │              │
┌───▼───┐    ┌──────▼──────┐    ┌───────▼───────┐     │
│DataIn-│    │Flink Metrics│    │  AgentServer  │     │
│gestor │    │ Aggregation │    │ (AI 诊断引擎)  │     │
│       │    │   Job       │    │  GLM-4 + MCP  │     │
└───┬───┘    └──────▲──────┘    └───────▲───────┘     │
    │               │                   │              │
    │        ┌──────┴──────┐    ┌───────┴───────┐     │
    ├───────►│    Kafka     │───►│Flink Anomaly │     │
    │        │(消息总线)    │    │Detection Job │     │
    │        └─────────────┘    └──────────────┘     │
    │                                                 │
    └────────────────►  InfluxDB (原始数据直写)  ◄─────┘
```

## 📁 项目结构

```
IAI/
├── AgentServer/              # AI 智能体服务
│   ├── api.py                # FastAPI 主入口
│   ├── agents/               # 智能体定义
│   │   ├── base_agent.py     # 基础 ReAct 循环（含错误去重）
│   │   ├── diagnostic_agent.py  # 诊断专家
│   │   └── decision_agent.py    # 决策专家
│   ├── services/
│   │   └── alert_service.py  # 告警管理（Redis 去重 + MySQL 落盘）
│   ├── models/
│   │   └── database.py       # 数据库连接池（MySQL + InfluxDB）
│   ├── mcp_server.py         # MCP 工具服务器（设备查询/遥测/知识库）
│   └── requirements.txt
│
├── DataIngestor/             # 数据采集服务
│   ├── sensor_simulator.py   # 传感器模拟器
│   ├── ingestor.py           # 双写逻辑（Kafka + InfluxDB）
│   └── config.py             # 配置文件
│
├── FlinkEngine/              # Flink 流计算引擎
│   ├── pom.xml               # Maven 构建配置（Flink 2.2.0）
│   └── src/main/java/com/iai/flink/
│       ├── AnomalyDetectionJob.java   # 异常检测作业
│       ├── MetricsAggregationJob.java # 指标聚合作业
│       └── sinks/InfluxDBSink.java    # InfluxDB 自定义 Sink
│
├── deploy/                   # 部署配置
│   ├── init-sql/init.sql     # MySQL 初始化脚本
│   └── grafana/              # Grafana 配置脚本
│
├── docker-compose.yml        # 全栈一键部署
└── docs/
    └── architecture_design.md
```

## 🚀 快速部署

### 前置要求
- Docker & Docker Compose
- Python 3.10+
- 智谱AI API Key ([获取地址](https://open.bigmodel.cn))

### 1. 启动基础设施

```bash
git clone https://github.com/Fengxiangrong-Boop/iai.git
cd iai

# 一键启动所有中间件
docker-compose up -d

# 等待服务就绪（约 30 秒）
sleep 30
docker-compose ps
```

### 2. 启动 AgentServer

```bash
cd AgentServer
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的智谱 AI API Key

# 启动服务
nohup python api.py > api_server.log 2>&1 &
```

### 3. 编译部署 Flink 作业

```bash
# 使用 Docker Maven 编译（无需本地安装 Java）
docker run --rm \
  -v $(pwd)/FlinkEngine:/app \
  -v ~/.m2:/root/.m2 \
  -w /app \
  maven:3.9-eclipse-temurin-17 \
  mvn clean package -DskipTests -s settings.xml

# 上传 JAR 到 Flink 集群
curl -X POST http://localhost:8081/jars/upload \
     -H "Expect:" \
     -F "jarfile=@FlinkEngine/target/FlinkEngine-1.0-SNAPSHOT.jar"

# 获取 JAR ID 并启动作业
JAR_ID=$(curl -s http://localhost:8081/jars | python3 -c "import sys,json; print(json.load(sys.stdin)['files'][0]['id'])")

curl -X POST "http://localhost:8081/jars/$JAR_ID/run" \
     -H "Content-Type: application/json" \
     -d '{"entryClass": "com.iai.flink.AnomalyDetectionJob"}'

curl -X POST "http://localhost:8081/jars/$JAR_ID/run" \
     -H "Content-Type: application/json" \
     -d '{"entryClass": "com.iai.flink.MetricsAggregationJob"}'
```

### 4. 配置 Grafana 大屏

```bash
bash deploy/grafana/setup_grafana.sh
# 访问 http://localhost:3000（admin / admin123）
```

### 5. 启动数据模拟

```bash
cd DataIngestor
python sensor_simulator.py
```

## 🔌 服务端口

| 服务 | 端口 | 用途 |
|------|------|------|
| AgentServer | 8000 | AI 诊断 API |
| Kafka | 9092 | 消息队列 |
| InfluxDB | 8086 | 时序数据库 |
| MySQL | 3306 | 关系型数据库 |
| Redis | 6379 | 告警去重缓存 |
| Nacos | 8848 | 服务注册中心 |
| Flink Dashboard | 8081 | 流计算管理 |
| Grafana | 3000 | 可视化大屏 |

## 🧪 API 测试

```bash
# 发送告警测试
curl -X POST http://localhost:8000/api/v1/alerts \
     -H "Content-Type: application/json" \
     -d '{
  "device_id": "PUMP_01",
  "status": "ANOMALY",
  "temperature": 92.3,
  "vibration": 3.5,
  "timestamp": "2026-02-28T06:53:00Z"
}'

# 查看诊断日志
tail -f AgentServer/api_server.log
```

## 🛠️ 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| AI 引擎 | 智谱 GLM-4 + MCP Protocol | Latest |
| API 框架 | FastAPI + Uvicorn | 0.100+ |
| 流计算 | Apache Flink | 2.2.0 |
| 消息队列 | Apache Kafka | Latest |
| 时序数据库 | InfluxDB | 1.8 |
| 关系型数据库 | MySQL | 8.0 |
| 缓存 | Redis | 7.x |
| 服务注册 | Nacos | 2.4.3 |
| 可视化 | Grafana | 12.4+ |
| 构建工具 | Maven + Docker | - |

## 📄 License

MIT License - 详见 [LICENSE](LICENSE)
