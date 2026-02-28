-- ================================
-- IAI System - MySQL Schema v2.0
-- ================================

CREATE DATABASE IF NOT EXISTS iai DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE iai;

-- 1. 设备档案表 (Device Registry)
CREATE TABLE IF NOT EXISTS device_registry (
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

-- 初始化测试数据
INSERT IGNORE INTO device_registry (device_id, device_name, device_type, model, factory_id, line_id, location, install_date, rated_temp_max, rated_vibration_max) VALUES 
('PUMP_01', '一号冷却泵', 'pump', 'QW-100', 'F001', 'L003', '车间A区', '2023-01-15', 65.0, 1.2),
('PUMP_02', '二号出水泵', 'pump', 'QW-150', 'F001', 'L003', '车间B区', '2022-11-20', 70.0, 1.5),
('PUMP_03', '三号备用泵', 'pump', 'QW-100', 'F001', 'L003', '车间A区', '2024-02-10', 65.0, 1.2);

-- 2. 告警记录表 (Alert Log)
CREATE TABLE IF NOT EXISTS alert_log (
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

-- 3. 诊断报告表 (Diagnosis Report)
CREATE TABLE IF NOT EXISTS diagnosis_report (
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

-- 4. 维保工单表 (Work Order)
CREATE TABLE IF NOT EXISTS work_order (
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

-- 5. 维保知识库 (Maintenance KB)
CREATE TABLE IF NOT EXISTS maintenance_kb (
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

-- 初始化测试诊断知识数据
INSERT IGNORE INTO maintenance_kb (device_type, fault_pattern, symptoms, root_cause, solution, prevention) VALUES 
('pump', '轴承磨损异响', '震动大于1.2G，温度升高超过65度，有异常噪音', '润滑不良或长期过载导致轴承滚珠磨损', '停机更换前端轴承，重新加注高温润滑脂', '定期（每月）检查并补充润滑油'),
('pump', '机械密封漏水', '泵体下部有持续滴水，偶尔伴随压力不稳', '密封环老化或含有杂质颗粒磨损密封面', '解体更换机械密封总成，清理泵腔内杂质', '检查进水过滤网，防止较大颗粒进入泵体');
