#!/bin/bash
# ============================================
# IAI 应用层启动脚本
# ============================================
# 职责划分:
#   基础设施:  docker compose up -d / down
#   应用服务:  bash start_all.sh / stop_all.sh （本脚本）
#   传感器:    cd DataIngestor && python sensor_simulator.py（手动控制）
# ============================================

set -e
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 敏感配置（可通过环境变量覆盖）
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-mysql@123}"
GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-admin123}"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   🏭 IAI 应用层服务启动                     ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ========================================
# 0. 检查 Docker 基础设施
# ========================================
echo -e "${GREEN}[0/5]${NC} 🐳 检查 Docker 基础设施..."
RUNNING=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -cE "kafka|mysql|influxdb|redis" || echo "0")
if [ "$RUNNING" -lt 3 ] 2>/dev/null; then
    echo -e "  ${RED}❌ Docker 基础设施未启动！请先执行:${NC}"
    echo -e "     ${YELLOW}cd $PROJECT_DIR && docker compose up -d${NC}"
    exit 1
fi
echo -e "  ${GREEN}✅${NC} 基础设施正常 ($RUNNING 个核心服务运行中)"

# ========================================
# 1. 初始化 MySQL（首次自动建表）
# ========================================
echo -e "${GREEN}[1/5]${NC} 🗄️  检查 MySQL..."
INIT_SQL="$PROJECT_DIR/deploy/init-sql/init.sql"
if [ -f "$INIT_SQL" ]; then
    TABLE_COUNT=$(docker exec mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='iai'" -s -N 2>/dev/null || echo "0")
    if [ "$TABLE_COUNT" -lt 3 ] 2>/dev/null; then
        echo "  📥 首次初始化数据库..."
        docker exec -i mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" iai < "$INIT_SQL" 2>/dev/null || true
        echo -e "  ${GREEN}✅${NC} MySQL 初始化完成"
    else
        echo -e "  ${GREEN}✅${NC} MySQL 已就绪 (${TABLE_COUNT} 张表)"
    fi
fi

# ========================================
# 2. 启动 AgentServer
# ========================================
echo -e "${GREEN}[2/5]${NC} 🧠 启动 AgentServer..."
cd "$PROJECT_DIR/AgentServer"

kill $(pgrep -f "python api.py" 2>/dev/null) 2>/dev/null || true
sleep 1

pip install -r requirements.txt -q 2>/dev/null || true

nohup python api.py > api_server.log 2>&1 &
AGENT_PID=$!
sleep 3
echo -e "  ${GREEN}✅${NC} AgentServer 已启动 (PID: $AGENT_PID)"

# ========================================
# 3. 提交 Flink 作业
# ========================================
echo -e "${GREEN}[3/5]${NC} ⚡ 提交 Flink 作业..."
FLINK_URL="http://127.0.0.1:8081"
FLINK_JAR="$PROJECT_DIR/FlinkEngine/target/FlinkEngine-1.0-SNAPSHOT.jar"

# 预创建 Kafka topic（Flink 需要 topic 已存在才能订阅）
echo "  📦 预创建 Kafka Topic..."
docker exec kafka kafka-topics.sh --create --if-not-exists \
    --topic raw_sensor_data --partitions 1 --replication-factor 1 \
    --bootstrap-server kafka:9092 2>/dev/null || true
docker exec kafka kafka-topics.sh --create --if-not-exists \
    --topic anomaly_alerts --partitions 1 --replication-factor 1 \
    --bootstrap-server kafka:9092 2>/dev/null || true

# 等待 Flink 就绪（最多 60 秒）
FLINK_WAIT=0
while ! curl -s "$FLINK_URL/overview" > /dev/null 2>&1; do
    if [ $FLINK_WAIT -ge 60 ]; then
        break
    fi
    echo -ne "  ⏳ 等待 Flink 启动... ${FLINK_WAIT}s\r"
    sleep 5
    FLINK_WAIT=$((FLINK_WAIT + 5))
done

if curl -s "$FLINK_URL/overview" > /dev/null 2>&1; then
    RUNNING_JOBS=$(curl -s "$FLINK_URL/jobs/overview" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(len([j for j in data.get('jobs', []) if j['state'] == 'RUNNING']))
except: print('0')
" 2>/dev/null)

    if [ "$RUNNING_JOBS" -ge 2 ] 2>/dev/null; then
        echo -e "  ${GREEN}✅${NC} Flink 作业已在运行 ($RUNNING_JOBS 个)"
    elif [ -f "$FLINK_JAR" ]; then
        echo "  📦 上传并启动 Flink 作业..."
        JAR_RESP=$(curl -s -X POST "$FLINK_URL/jars/upload" -H "Expect:" -F "jarfile=@$FLINK_JAR" 2>/dev/null)
        JAR_ID=$(echo "$JAR_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('filename','').split('/')[-1])" 2>/dev/null)

        if [ -n "$JAR_ID" ] && [ "$JAR_ID" != "None" ]; then
            curl -s -X POST "$FLINK_URL/jars/$JAR_ID/run" -H "Content-Type: application/json" \
                 -d '{"entryClass": "com.iai.flink.AnomalyDetectionJob"}' > /dev/null 2>&1
            curl -s -X POST "$FLINK_URL/jars/$JAR_ID/run" -H "Content-Type: application/json" \
                 -d '{"entryClass": "com.iai.flink.MetricsAggregationJob"}' > /dev/null 2>&1
            sleep 3
            echo -e "  ${GREEN}✅${NC} 2 个 Flink 作业已提交"
        else
            echo -e "  ${RED}❌${NC} JAR 上传失败"
        fi
    else
        echo -e "  ${YELLOW}⚠️${NC}  未找到 JAR，请先编译 FlinkEngine"
    fi
else
    echo -e "  ${YELLOW}⚠️${NC}  Flink 不可达，跳过"
fi

# ========================================
# 4. 初始化 Grafana 看板（首次自动配置）
# ========================================
echo -e "${GREEN}[4/5]${NC} 📊 检查 Grafana 看板..."
GRAFANA_URL="http://127.0.0.1:3000"
DASHBOARD_CHECK=$(curl -s -u admin:$GRAFANA_ADMIN_PASSWORD "$GRAFANA_URL/api/search?query=IAI" 2>/dev/null)
HAS_DASHBOARD=$(echo "$DASHBOARD_CHECK" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(len(data))
except: print('0')
" 2>/dev/null)

if [ "$HAS_DASHBOARD" -gt 0 ] 2>/dev/null; then
    echo -e "  ${GREEN}✅${NC} Grafana 看板已就绪"
else
    echo "  📥 首次配置 Grafana 数据源和看板..."
    bash "$PROJECT_DIR/deploy/grafana/setup_grafana.sh" > /dev/null 2>&1 || true
    bash "$PROJECT_DIR/deploy/grafana/update_dashboard.sh" > /dev/null 2>&1 || true
    echo -e "  ${GREEN}✅${NC} Grafana 看板初始化完成"
fi

# ========================================
# 5. 启动传感器模拟器
# ========================================
echo -e "${GREEN}[5/5]${NC} 📡 启动传感器模拟器..."
cd "$PROJECT_DIR/DataIngestor"
kill $(pgrep -f "sensor_simulator" 2>/dev/null) 2>/dev/null || true
sleep 1
nohup python sensor_simulator.py > simulator.log 2>&1 &
SIM_PID=$!
echo -e "  ${GREEN}✅${NC} 传感器模拟器已启动 (PID: $SIM_PID)"
echo -e "  📋 日志: $PROJECT_DIR/DataIngestor/simulator.log"

# ========================================
# 完成
# ========================================
echo ""
echo "═══════════════════════════════════════════════"
echo -e " ${GREEN}🎉 全部服务启动完成！${NC}"
echo ""
echo " 📊 Grafana 大屏:  http://192.168.0.105:3000"
echo " 🧠 管理后台:      http://192.168.0.105:8000/dashboard"
echo " 📖 API 文档:      http://192.168.0.105:8000/docs"
echo " ⚡ Flink 控制台:  http://192.168.0.105:8081"
echo " 🔧 Nacos 控制台:  http://192.168.0.105:8848"
echo " 📡 Kafka 浏览器:  http://192.168.0.105:9000"
echo ""
