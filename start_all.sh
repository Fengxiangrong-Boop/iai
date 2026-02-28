#!/bin/bash
# ============================================
# IAI 工业智能体系统 - 全栈启动脚本
# ============================================
# 用法:
#   bash start_all.sh           # 启动全部（不含传感器模拟）
#   bash start_all.sh --with-simulator  # 启动全部 + 传感器模拟（会触发大模型调用！）
# ============================================

set -e
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   🏭 IAI 工业智能体系统 - 全栈启动          ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ========================================
# 1. 启动 Docker 基础设施
# ========================================
echo -e "${GREEN}[1/5]${NC} 🐳 启动 Docker 基础设施 (Kafka/InfluxDB/MySQL/Redis/Nacos/Flink/Grafana)..."
if [ -f "$PROJECT_DIR/docker-compose.yml" ]; then
    cd "$PROJECT_DIR"
    docker-compose up -d 2>/dev/null || docker compose up -d 2>/dev/null
    echo -e "  ${GREEN}✅${NC} Docker 基础设施已启动"
else
    echo -e "  ${YELLOW}⚠️${NC}  未找到 docker-compose.yml，跳过（假设基础设施已手动启动）"
fi

# 等待服务就绪
echo "  ⏳ 等待服务就绪 (15秒)..."
sleep 15

# ========================================
# 2. 初始化 MySQL（如果需要）
# ========================================
echo -e "${GREEN}[2/5]${NC} 🗄️  检查 MySQL 初始化..."
INIT_SQL="$PROJECT_DIR/deploy/init-sql/init.sql"
if [ -f "$INIT_SQL" ]; then
    # 尝试检查 iai 数据库是否已初始化
    TABLE_COUNT=$(docker exec mysql mysql -uroot -p'mysql@123' -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='iai'" -s -N 2>/dev/null || echo "0")
    if [ "$TABLE_COUNT" -lt 3 ] 2>/dev/null; then
        echo "  📥 正在初始化 MySQL 数据库..."
        docker exec -i mysql mysql -uroot -p'mysql@123' iai < "$INIT_SQL" 2>/dev/null || true
        echo -e "  ${GREEN}✅${NC} MySQL 初始化完成"
    else
        echo -e "  ${GREEN}✅${NC} MySQL 已初始化 (${TABLE_COUNT} 张表)"
    fi
else
    echo -e "  ${YELLOW}⚠️${NC}  未找到 init.sql，跳过"
fi

# ========================================
# 3. 启动 AgentServer
# ========================================
echo -e "${GREEN}[3/5]${NC} 🧠 启动 AgentServer (AI 诊断引擎)..."
cd "$PROJECT_DIR/AgentServer"

# 停掉旧进程（如果存在）
kill $(pgrep -f "python api.py" 2>/dev/null) 2>/dev/null || true
sleep 1

# 安装依赖（静默）
pip install -r requirements.txt -q 2>/dev/null || true

# 启动
nohup python api.py > api_server.log 2>&1 &
AGENT_PID=$!
echo -e "  ${GREEN}✅${NC} AgentServer 已启动 (PID: $AGENT_PID)"
echo "  📋 日志: $PROJECT_DIR/AgentServer/api_server.log"
echo "  🌐 管理后台: http://192.168.0.105:8000/dashboard"
echo "  📖 API 文档: http://192.168.0.105:8000/docs"

# 等待 AgentServer 就绪
sleep 5

# ========================================
# 4. 提交 Flink 作业
# ========================================
echo -e "${GREEN}[4/5]${NC} ⚡ 检查 Flink 作业状态..."
FLINK_URL="http://127.0.0.1:8081"
FLINK_JAR="$PROJECT_DIR/FlinkEngine/target/FlinkEngine-1.0-SNAPSHOT.jar"

# 检查 Flink 是否可达
if curl -s "$FLINK_URL/overview" > /dev/null 2>&1; then
    # 检查是否有正在运行的作业
    RUNNING_JOBS=$(curl -s "$FLINK_URL/jobs/overview" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    running = [j for j in data.get('jobs', []) if j['state'] == 'RUNNING']
    print(len(running))
except: print('0')
" 2>/dev/null)

    if [ "$RUNNING_JOBS" -ge 2 ] 2>/dev/null; then
        echo -e "  ${GREEN}✅${NC} Flink 作业已在运行中 ($RUNNING_JOBS 个)"
    elif [ -f "$FLINK_JAR" ]; then
        echo "  📦 上传 Flink JAR..."
        JAR_RESP=$(curl -s -X POST "$FLINK_URL/jars/upload" -H "Expect:" -F "jarfile=@$FLINK_JAR" 2>/dev/null)
        JAR_ID=$(echo "$JAR_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('filename','').split('/')[-1])" 2>/dev/null)

        if [ -n "$JAR_ID" ] && [ "$JAR_ID" != "None" ]; then
            echo "  🚀 启动 AnomalyDetectionJob..."
            curl -s -X POST "$FLINK_URL/jars/$JAR_ID/run" \
                 -H "Content-Type: application/json" \
                 -d '{"entryClass": "com.iai.flink.AnomalyDetectionJob"}' > /dev/null 2>&1

            echo "  🚀 启动 MetricsAggregationJob..."
            curl -s -X POST "$FLINK_URL/jars/$JAR_ID/run" \
                 -H "Content-Type: application/json" \
                 -d '{"entryClass": "com.iai.flink.MetricsAggregationJob"}' > /dev/null 2>&1

            sleep 3
            echo -e "  ${GREEN}✅${NC} Flink 作业已提交"
        else
            echo -e "  ${RED}❌${NC} JAR 上传失败"
        fi
    else
        echo -e "  ${YELLOW}⚠️${NC}  未找到编译好的 JAR，请先运行 Maven 编译"
    fi
else
    echo -e "  ${YELLOW}⚠️${NC}  Flink 不可达，跳过作业提交"
fi

# ========================================
# 5. 传感器模拟器（可选，默认不启动）
# ========================================
echo -e "${GREEN}[5/5]${NC} 📡 传感器模拟器..."
if [ "$1" = "--with-simulator" ]; then
    echo -e "  ${YELLOW}⚠️  注意: 模拟器将触发 Flink→AgentServer→大模型调用（会产生 API 费用）${NC}"
    cd "$PROJECT_DIR/DataIngestor"
    kill $(pgrep -f "sensor_simulator" 2>/dev/null) 2>/dev/null || true
    nohup python sensor_simulator.py > simulator.log 2>&1 &
    SIM_PID=$!
    echo -e "  ${GREEN}✅${NC} 传感器模拟器已启动 (PID: $SIM_PID)"
    echo "  📋 日志: $PROJECT_DIR/DataIngestor/simulator.log"
else
    echo -e "  ⏭️  跳过（如需启动请加 ${YELLOW}--with-simulator${NC} 参数）"
    echo -e "  💡 单独启动: cd DataIngestor && python sensor_simulator.py"
fi

# ========================================
# 输出总览
# ========================================
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   🎉 IAI 系统启动完成!                      ║"
echo "╠══════════════════════════════════════════════╣"
echo "║                                              ║"
echo "║   📊 Grafana 大屏: http://192.168.0.105:3000 ║"
echo "║   🧠 管理后台:     http://192.168.0.105:8000/dashboard  ║"
echo "║   📖 API 文档:     http://192.168.0.105:8000/docs       ║"
echo "║   ⚡ Flink 控制台: http://192.168.0.105:8081 ║"
echo "║   🔧 Nacos 控制台: http://192.168.0.105:8848 ║"
echo "║                                              ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
