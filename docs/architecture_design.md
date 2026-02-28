# 🏭 IAI — 工业实时智能决策系统 (Industrial AI Intelligence)

## 企业级架构设计方案 v2.0

> **文档版本**: v2.0  
> **设计标准**: 企业生产级  
> **目标环境**: 单台服务器（35GB RAM / 913GB SSD / 192.168.0.105）  
> **最后更新**: 2026-02-28

---

## 一、系统定位与目标

### 1.1 系统定位
本系统是一套面向工业制造场景的 **实时智能决策平台**，核心解决以下问题：

- **实时感知**：秒级采集工业设备传感器数据
- **实时检测**：毫秒级异常检测与告警分级
- **智能诊断**：AI 多智能体自动化根因分析
- **辅助决策**：自动生成维保工单和决策建议
- **历史追溯**：时序数据归档、趋势分析、故障回溯

### 1.2 核心指标（SLA）

| 指标 | 目标值 |
|---|---|
| 数据采集延迟 | ≤ 1s（从传感器到 Kafka） |
| 异常检测延迟 | ≤ 3s（从 Kafka 到告警触发） |
| AI 诊断响应 | ≤ 30s（告警到维保报告生成） |
| 系统可用性 | ≥ 99.5%（单机部署标准） |
| 数据保留期 | 原始数据 90 天，聚合数据 1 年 |
| 并发设备数 | ≥ 100 台传感器 |

---

## 二、整体架构

### 2.1 分层架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         📊 展示层 (Presentation)                        │
│                                                                         │
│   Grafana (实时监控大屏)    │   Web Console (告警管理)    │   API 开放    │
│   端口: 3000               │   端口: 3001               │   端口: 8000  │
└───────────────────────────┬─────────────────────────────┬───────────────┘
                            │                             │
┌───────────────────────────▼─────────────────────────────▼───────────────┐
│                       🧠 智能决策层 (Intelligence)                       │
│                                                                         │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────────┐  │
│  │  AgentServer     │  │  DiagnosticAgent │  │  DecisionAgent        │  │
│  │  (FastAPI)       │  │  (诊断专家)      │  │  (维保决策专家)       │  │
│  │  Port: 8000      │  │  GLM-4 + MCP     │  │  GLM-4               │  │
│  └──────┬───────────┘  └──────────────────┘  └───────────────────────┘  │
│         │                                                               │
│  ┌──────▼───────────────────────────────────────────────────────────┐   │
│  │                MCP Server (工具/技能库)                           │   │
│  │  query_device_status()  → MySQL                                  │   │
│  │  fetch_telemetry_data() → InfluxDB                               │   │
│  │  search_maintenance_kb()→ MySQL                                  │   │
│  │  get_alert_history()    → MySQL (新增)                           │   │
│  │  predict_failure()      → ML Model API (新增)                    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────────┐
│                       ⚡ 实时计算层 (Stream Processing)                  │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Flink Cluster (v2.2.0)                       │    │
│  │                                                                 │    │
│  │  Job 1: AnomalyDetectionJob (实时异常检测)                      │    │
│  │    └─ Kafka Source → Filter → HttpWebhookSink → AgentServer     │    │
│  │                                                                 │    │
│  │  Job 2: MetricsAggregationJob (指标聚合) [新增]                 │    │
│  │    └─ Kafka Source → Window(1min) → InfluxDB Sink               │    │
│  │                                                                 │    │
│  │  Job 3: AlertDeduplicationJob (告警去重) [新增]                  │    │
│  │    └─ 同一设备 5 分钟内不重复告警                                │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────────┐
│                       📦 消息与存储层 (Data Infrastructure)              │
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Kafka      │  │  InfluxDB   │  │   MySQL      │  │   Redis      │  │
│  │   Port: 9092 │  │  Port: 8086 │  │   Port: 3306 │  │   Port: 6379 │  │
│  │             │  │             │  │              │  │              │  │
│  │  Topics:    │  │  数据:      │  │  数据:       │  │  数据:       │  │
│  │  • raw_     │  │  • 原始时序 │  │  • 设备档案  │  │  • 告警去重  │  │
│  │    sensor_  │  │  • 聚合指标 │  │  • 维保记录  │  │  • 诊断缓存  │  │
│  │    data     │  │  • 异常标记 │  │  • 告警日志  │  │  • 会话状态  │  │
│  │  • alerts   │  │             │  │  • 诊断报告  │  │              │  │
│  └─────────────┘  └─────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────────┐
│                       🔌 数据接入层 (Data Ingestion)                     │
│                                                                         │
│  ┌─────────────────────┐  ┌──────────────────────────────────────────┐  │
│  │  DataIngestor       │  │  协议适配器 (未来扩展)                   │  │
│  │  (Python)           │  │  • MQTT Adapter (温湿度传感器)           │  │
│  │                     │  │  • Modbus Adapter (PLC/工控)             │  │
│  │  功能:              │  │  • OPC-UA Adapter (SCADA)                │  │
│  │  • 读取真实传感器   │  │                                          │  │
│  │  • 数据清洗/校验    │  │                                          │  │
│  │  • 双写 Kafka +     │  │                                          │  │
│  │    InfluxDB         │  │                                          │  │
│  └─────────────────────┘  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流全链路

```
传感器/模拟器 (DataIngestor)
    │
    ├──── 写入 ────→ Kafka (raw_sensor_data)
    │                    │
    │                    ├──→ Flink Job 1: 异常检测
    │                    │       │
    │                    │       ├─ 正常数据 → 丢弃
    │                    │       │
    │                    │       └─ 异常数据 → Redis 去重判断
    │                    │                       │
    │                    │                  ┌────┴────┐
    │                    │                  │ 首次？  │
    │                    │                  └────┬────┘
    │                    │                   是  │  否
    │                    │                   ↓   │   ↓
    │                    │       AgentServer ←┘   丢弃(5分钟冷却)
    │                    │           │
    │                    │           ├→ 诊断专家 (查 InfluxDB真实历史)
    │                    │           ├→ 诊断专家 (查 MySQL设备档案)
    │                    │           ├→ 决策专家 (生成维保方案)
    │                    │           │
    │                    │           └→ MySQL (保存诊断报告)
    │                    │
    │                    └──→ Flink Job 2: 指标聚合 (1分钟窗口)
    │                            │
    │                            └──→ InfluxDB (aggregated_metrics)
    │
    └──── 写入 ────→ InfluxDB (raw_sensor_data, 原始归档)
```

---

## 三、各层详细设计

### 3.1 数据接入层 — DataIngestor

**职责**：采集传感器原始数据，校验后双写。

```python
# 核心逻辑伪代码
class DataIngestor:
    """
    数据采集器：从传感器读取数据，清洗后双写到 Kafka 和 InfluxDB。
    
    输入: 传感器原始信号 (温度/振动/压力/电流等)
    输出: 
        - Kafka topic "raw_sensor_data": JSON 格式实时流
        - InfluxDB measurement "sensor_raw": 时序归档
    """
    
    def ingest(self, sensor_reading):
        # 1. 数据校验（过滤无效值、越界检查）
        validated = self.validate(sensor_reading)
        
        # 2. 写入 Kafka（实时流处理通道）
        self.kafka_producer.send("raw_sensor_data", validated.to_json())
        
        # 3. 写入 InfluxDB（历史归档通道）
        self.influx_client.write("sensor_raw", validated.to_line_protocol())
```

**数据模型（JSON）**:
```json
{
    "device_id": "PUMP_01",
    "timestamp": "2026-02-28T12:00:00.000Z",
    "temperature": 45.3,
    "vibration": 0.52,
    "pressure": 2.1,
    "current": 15.8,
    "status": "NORMAL",
    "factory_id": "F001",
    "line_id": "L003"
}
```

### 3.2 消息与存储层

#### 3.2.1 Kafka — 实时消息总线

| 配置项 | 值 | 说明 |
|---|---|---|
| Topic | `raw_sensor_data` | 原始传感器数据 |
| Topic | `alerts` | 告警事件（新增选项） |
| Partitions | 3 | 按 device_id 分区，保证同设备顺序 |
| Retention | 24h | 只保留一天，历史数据在 InfluxDB |
| Replication | 1 | 单机部署，无需副本 |

#### 3.2.2 InfluxDB — 时序数据库

| Measurement | 数据内容 | 保留策略 |
|---|---|---|
| `sensor_raw` | 原始传感器读数 | 90 天（自动过期） |
| `sensor_agg_1m` | 1 分钟聚合指标（Flink 写入） | 365 天 |
| `anomaly_events` | 异常事件标记 | 365 天 |

```sql
-- InfluxDB 保留策略配置
CREATE RETENTION POLICY "rp_raw_90d" ON "iai" DURATION 90d REPLICATION 1 DEFAULT
CREATE RETENTION POLICY "rp_agg_365d" ON "iai" DURATION 365d REPLICATION 1
```

#### 3.2.3 MySQL — 关系型数据库

```sql
-- ================================
-- 1. 设备档案表 (Device Registry)
-- ================================
CREATE TABLE device_registry (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    device_id       VARCHAR(50) NOT NULL UNIQUE COMMENT '设备唯一编号',
    device_name     VARCHAR(100) NOT NULL COMMENT '设备名称',
    device_type     VARCHAR(50) NOT NULL COMMENT '设备类型: pump/motor/compressor',
    model           VARCHAR(100) COMMENT '设备型号',
    manufacturer    VARCHAR(100) COMMENT '制造商',
    factory_id      VARCHAR(50) NOT NULL COMMENT '工厂编号',
    line_id         VARCHAR(50) NOT NULL COMMENT '产线编号',
    location        VARCHAR(200) COMMENT '安装位置',
    install_date    DATE COMMENT '安装日期',
    rated_temp_max  DECIMAL(6,2) COMMENT '额定最高温度 (°C)',
    rated_vibration_max DECIMAL(6,2) COMMENT '额定最大振动 (G)',
    rated_pressure_max  DECIMAL(6,2) COMMENT '额定最大压力 (MPa)',
    status          ENUM('RUNNING','STOPPED','MAINTENANCE','RETIRED') DEFAULT 'RUNNING',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_factory_line (factory_id, line_id),
    INDEX idx_device_type (device_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='设备基础档案';

-- ================================
-- 2. 告警记录表 (Alert Log)
-- ================================
CREATE TABLE alert_log (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id        VARCHAR(64) NOT NULL UNIQUE COMMENT '链路追踪ID',
    device_id       VARCHAR(50) NOT NULL COMMENT '设备编号',
    alert_level     ENUM('P0','P1','P2','P3') NOT NULL COMMENT '告警等级',
    alert_type      VARCHAR(50) COMMENT '告警类型: over_temp/high_vibration/composite',
    temperature     DECIMAL(6,2) COMMENT '触发时温度',
    vibration       DECIMAL(6,3) COMMENT '触发时振动值',
    raw_payload     JSON COMMENT 'Flink 原始告警数据',
    status          ENUM('PENDING','DIAGNOSING','COMPLETED','IGNORED') DEFAULT 'PENDING',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_device_time (device_id, created_at),
    INDEX idx_status (status),
    INDEX idx_level (alert_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='告警事件记录';

-- ================================
-- 3. 诊断报告表 (Diagnosis Report)
-- ================================
CREATE TABLE diagnosis_report (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id        VARCHAR(64) NOT NULL COMMENT '关联告警的追踪ID',
    device_id       VARCHAR(50) NOT NULL,
    diagnosis_text  TEXT NOT NULL COMMENT '诊断专家生成的报告全文',
    decision_text   TEXT COMMENT '决策专家生成的维保方案',
    fault_category  VARCHAR(100) COMMENT '故障分类: bearing/seal/motor/unknown',
    severity        ENUM('CRITICAL','HIGH','MEDIUM','LOW') COMMENT 'AI判定严重程度',
    recommended_action VARCHAR(500) COMMENT '建议操作摘要',
    llm_model       VARCHAR(50) COMMENT '使用的大模型名称',
    tokens_used     INT COMMENT '消耗的 Token 数',
    latency_ms      INT COMMENT '诊断耗时（毫秒）',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trace_id) REFERENCES alert_log(trace_id),
    INDEX idx_device (device_id),
    INDEX idx_fault (fault_category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI诊断报告';

-- ================================
-- 4. 维保工单表 (Work Order)
-- ================================
CREATE TABLE work_order (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_no        VARCHAR(50) NOT NULL UNIQUE COMMENT '工单编号: WO-20260228-001',
    trace_id        VARCHAR(64) COMMENT '关联告警追踪ID',
    device_id       VARCHAR(50) NOT NULL,
    order_type      ENUM('EMERGENCY','PLANNED','INSPECTION') NOT NULL COMMENT '工单类型',
    priority        ENUM('P0','P1','P2','P3') NOT NULL,
    description     TEXT NOT NULL COMMENT '工单描述',
    assigned_to     VARCHAR(100) COMMENT '指派人员',
    status          ENUM('OPEN','IN_PROGRESS','COMPLETED','CANCELLED') DEFAULT 'OPEN',
    estimated_hours DECIMAL(5,1) COMMENT '预计工时',
    actual_hours    DECIMAL(5,1) COMMENT '实际工时',
    materials       JSON COMMENT '所需物料清单',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP NULL,
    INDEX idx_device (device_id),
    INDEX idx_status_priority (status, priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='维保工单';

-- ================================
-- 5. 维保知识库 (Maintenance KB)
-- ================================
CREATE TABLE maintenance_kb (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    device_type     VARCHAR(50) NOT NULL COMMENT '适用设备类型',
    fault_pattern   VARCHAR(200) NOT NULL COMMENT '故障模式描述',
    symptoms        TEXT COMMENT '典型症状特征',
    root_cause      TEXT COMMENT '根因分析',
    solution        TEXT COMMENT '解决方案',
    prevention      TEXT COMMENT '预防措施',
    source          ENUM('MANUAL','AI_GENERATED','VENDOR') DEFAULT 'MANUAL',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_device_type (device_type),
    FULLTEXT INDEX ft_search (fault_pattern, symptoms, root_cause, solution)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='维保专家知识库';
```

#### 3.2.4 Redis — 缓存与状态管理

| Key 模式 | 用途 | TTL |
|---|---|---|
| `alert:dedup:{device_id}` | 告警去重冷却 | 5 分钟 |
| `diag:cache:{trace_id}` | 诊断结果缓存 | 1 小时 |
| `device:status:{device_id}` | 设备实时状态缓存 | 30 秒 |
| `rate:limit:{device_id}` | 单设备告警限流 | 1 分钟 |

### 3.3 实时计算层 — Flink

#### Job 1: AnomalyDetectionJob（已完成 ✅）
- 从 Kafka 消费原始数据
- 过滤 `status == "ANOMALY"` 的记录
- 通过 HTTP Webhook 发送至 AgentServer

#### Job 2: MetricsAggregationJob（新增 🆕）
- 从 Kafka 消费原始数据
- 按 `device_id` 分组，1 分钟滚动窗口
- 聚合计算：avg / max / min / count
- 写入 InfluxDB `sensor_agg_1m` measurement

#### Job 3: AlertDeduplicationJob（新增 🆕，可选方案）
- 在 Job 1 的基础上增加窗口去重
- 使用 Flink 的 `KeyedProcessFunction` 状态管理
- 同一设备 5 分钟内只触发一次告警
- （替代 Redis 去重，纯流处理实现）

### 3.4 智能决策层 — AgentServer

#### 3.4.1 核心改进

| 模块 | 当前状态 | 升级方案 |
|---|---|---|
| MCP Tools | Mock 假数据 | 对接真实 MySQL + InfluxDB |
| 诊断结果 | 仅打印日志 | 写入 MySQL `diagnosis_report` 表 |
| 告警管理 | 无记录 | 写入 MySQL `alert_log` 表 |
| 工单生成 | 无 | 自动写入 `work_order` 表 |
| 去重机制 | 无 | Redis 5 分钟冷却窗口 |
| API 安全 | 无认证 | API Key / JWT 认证 |

#### 3.4.2 升级后的 MCP 工具清单

```python
# ====== 查询类工具（诊断专家使用）======

@mcp.tool()
def query_device_status(device_id: str) -> str:
    """查询设备基础档案和设计参数 → MySQL device_registry"""

@mcp.tool()
def fetch_telemetry_data(device_id: str, window_mins: int = 60) -> str:
    """查询设备历史遥测数据统计 → InfluxDB sensor_raw/sensor_agg_1m"""

@mcp.tool()
def search_maintenance_kb(device_type: str, keyword: str = "") -> str:
    """搜索维保知识库中的故障模式和解决方案 → MySQL maintenance_kb"""

@mcp.tool()
def get_alert_history(device_id: str, days: int = 7) -> str:
    """获取设备近期告警历史 → MySQL alert_log"""

# ====== 执行类工具（决策专家使用）======

@mcp.tool()
def create_work_order(device_id: str, priority: str, description: str) -> str:
    """创建维保工单 → MySQL work_order"""

@mcp.tool()
def update_device_status(device_id: str, status: str) -> str:
    """更新设备运行状态（如：标记为 MAINTENANCE）→ MySQL device_registry"""
```

### 3.5 展示层

#### 3.5.1 Grafana 监控大屏

| Dashboard | 数据源 | 核心图表 |
|---|---|---|
| **设备实时监控** | InfluxDB | 温度/振动实时折线图、设备状态看板 |
| **异常告警总览** | MySQL | 告警数量趋势、设备告警排名（Top10）|
| **AI 诊断分析** | MySQL | 诊断延迟分布、故障分类饼图、处理闭环率 |
| **全局概览** | 混合 | 在线设备数、今日告警、AI 处理率、平均响应时间 |

---

## 四、目录结构规划

```
IAI/
├── docs/                           # 项目文档
│   ├── architecture_design.md      # 本文档
│   └── api_reference.md            # API 接口文档
│
├── AgentServer/                    # 智能决策服务（Python）
│   ├── api.py                      # FastAPI 主入口
│   ├── mcp_server.py               # MCP 工具服务（对接真实DB）
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── diagnostic_agent.py     # 诊断专家
│   │   └── decision_agent.py       # 决策专家
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py              # Pydantic 数据模型
│   │   └── database.py             # MySQL/Redis/InfluxDB 连接管理
│   ├── services/
│   │   ├── __init__.py
│   │   ├── alert_service.py        # 告警管理（去重、入库、状态机）
│   │   ├── influx_service.py       # InfluxDB 读写封装
│   │   └── work_order_service.py   # 工单管理
│   ├── config/
│   │   └── settings.py             # 全局配置（Pydantic Settings）
│   ├── tests/
│   │   ├── test_api.py
│   │   ├── test_agents.py
│   │   └── test_services.py
│   ├── logger.py
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── .env
│
├── FlinkEngine/                    # 实时计算引擎（Java）
│   ├── src/main/java/com/iai/flink/
│   │   ├── AnomalyDetectionJob.java      # Job 1: 异常检测
│   │   ├── MetricsAggregationJob.java    # Job 2: 指标聚合 (新增)
│   │   └── sinks/
│   │       ├── HttpWebhookSink.java      # HTTP 输出
│   │       └── InfluxDBSink.java         # InfluxDB 输出 (新增)
│   ├── pom.xml
│   └── settings.xml
│
├── DataIngestor/                   # 数据接入服务（Python）
│   ├── ingestor.py                 # 核心采集逻辑
│   ├── sensor_simulator.py         # 模拟器（开发测试用）
│   ├── protocols/                  # 协议适配（未来扩展）
│   │   ├── mqtt_adapter.py
│   │   └── modbus_adapter.py
│   ├── config.py
│   └── requirements.txt
│
├── deploy/                         # 部署配置
│   ├── docker-compose.yml          # 完整编排文件
│   ├── init-sql/
│   │   └── init.sql                # MySQL 初始化脚本
│   ├── grafana/
│   │   └── dashboards/             # Grafana 预配置 Dashboard JSON
│   └── scripts/
│       ├── start_all.sh            # 一键启动
│       ├── stop_all.sh             # 一键停止
│       └── health_check.sh         # 健康检查
│
├── .gitignore
└── README.md
```

---

## 五、资源规划与容量评估

### 5.1 服务器资源分配（35GB RAM 总量）

| 服务 | CPU | 内存分配 | 说明 |
|---|---|---|---|
| **Kafka + Zookeeper** | 2 core | 2 GB | 消息吞吐量适中 |
| **Flink (JM + TM)** | 4 core | 4 GB | 3 个 Job 并行 |
| **InfluxDB** | 2 core | 3 GB | 时序读写密集 |
| **MySQL** | 2 core | 2 GB | 结构化查询 |
| **Redis** | 1 core | 512 MB | 缓存去重 |
| **Grafana** | 1 core | 512 MB | 实时渲染 |
| **AgentServer** | 2 core | 1 GB | AI Agent 服务 |
| **DataIngestor** | 1 core | 512 MB | 数据采集 |
| **Nacos** | 1 core | 1 GB | 配置中心 |
| **OS + 预留** | — | ~20 GB | 系统和缓冲 |
| **合计** | — | ~35 GB | 满配 |

### 5.2 磁盘容量估算

| 数据类型 | 单条大小 | 日增量 | 90天存储 |
|---|---|---|---|
| InfluxDB 原始数据 | ~200B | ~17 MB/天 (100设备×1条/秒) | ~1.5 GB |
| InfluxDB 聚合数据 | ~100B | ~14 MB/天 | ~1.3 GB |
| MySQL 告警+诊断 | ~2KB | ~20 MB/天 (假设1000条告警) | ~1.8 GB |
| Kafka 日志 | — | ~17 MB/天 (24h 保留) | 仅 17 MB |
| **总计** | — | — | **≈ 5 GB / 90天** |

> 913GB 磁盘空间极为充裕，**无需担心**。

---

## 六、实施路线图

### Phase 1: 数据层真实化（1-2 天）✅ 优先
> 目标：让 AI 查到真实数据，而非假数据

- [ ] MySQL 建表 + 初始化设备档案数据
- [ ] InfluxDB 创建数据库和保留策略
- [ ] `sensor_simulator.py` 升级为双写（Kafka + InfluxDB）
- [ ] `mcp_server.py` 对接真实 MySQL 和 InfluxDB
- [ ] 端到端验证：AI 诊断报告中引用真实数据

### Phase 2: 告警管理闭环（1 天）
> 目标：告警有记录、有去重、有工单

- [ ] Redis 告警去重（5 分钟冷却窗口）
- [ ] 告警入库 MySQL `alert_log`
- [ ] 诊断报告入库 MySQL `diagnosis_report`
- [ ] 自动生成维保工单 `work_order`

### Phase 3: Grafana 可视化（1 天）
> 目标：实时监控大屏

- [ ] 对接 InfluxDB 数据源，展示传感器趋势
- [ ] 对接 MySQL 数据源，展示告警和工单
- [ ] 配置自动刷新（5s 间隔）

### Phase 4: Flink 计算增强（1-2 天）
> 目标：更智能的流处理

- [ ] Job 2: 1 分钟窗口指标聚合写入 InfluxDB
- [ ] Job 3: 告警去重（可选，Flink 侧 or Redis 侧二选一）
- [ ] 异常检测规则优化（多维度组合判断）

### Phase 5: 生产加固（持续）
> 目标：稳定性和安全性

- [ ] API Key 认证
- [ ] 日志规范化 + ELK/Loki 收集
- [ ] 监控告警（Grafana Alerting）
- [ ] Docker Compose 统一编排
- [ ] 一键启停脚本
- [ ] 健康检查定时任务

---

## 七、技术选型总结

| 领域 | 选型 | 版本 | 选择理由 |
|---|---|---|---|
| 消息队列 | Kafka | 3.x | 高吞吐、行业标准、生态完善 |
| 流计算 | Flink | 2.2.0 | 毫秒级延迟、状态管理、窗口计算 |
| 时序数据库 | InfluxDB | 1.8 | 轻量级、InfluxQL 简单、适合单机 |
| 关系数据库 | MySQL | 8.0 | 设备档案、工单等结构化数据 |
| 缓存 | Redis | Alpine | 去重、限流、状态缓存 |
| AI 引擎 | GLM-4 | — | 中文优化、工具调用能力强 |
| Agent 框架 | MCP + ReAct | — | 标准化工具协议、多轮推理 |
| API 服务 | FastAPI | 0.100+ | 异步高性能、自动文档 |
| 可视化 | Grafana | Latest | 多数据源、丰富图表、告警集成 |
| 服务注册 | Nacos | 2.3.2 | 配置热更新、服务健康检查 |

---

## 八、风险控制

| 风险项 | 影响 | 缓解措施 |
|---|---|---|
| 单机故障 | 全系统不可用 | Docker 自动重启 + UPS电源 + 定期备份 |
| LLM API 不可用 | AI 诊断失败 | 降级为规则引擎预设方案 + 重试机制 |
| Kafka 数据积压 | 处理延迟 | 监控 Consumer Lag + 告警 |
| InfluxDB 磁盘满 | 数据丢失 | 自动保留策略 + 磁盘监控 |
| 告警风暴 | AgentServer 过载 | Redis 去重 + 限流 + 批量合并 |
