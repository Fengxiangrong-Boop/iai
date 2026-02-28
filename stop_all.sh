#!/bin/bash
# ============================================
# IAI 应用层停止脚本
# ============================================
# 职责划分:
#   基础设施:  docker compose down
#   应用服务:  bash stop_all.sh （本脚本）
#   传感器:    kill $(pgrep -f sensor_simulator)
# ============================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   🛑 IAI 应用层服务停止                     ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# 1. 停止传感器模拟器（如果有）
echo -e "${GREEN}[1/3]${NC} 📡 停止传感器模拟器..."
SIM_PIDS=$(pgrep -f "sensor_simulator" 2>/dev/null)
if [ -n "$SIM_PIDS" ]; then
    kill $SIM_PIDS 2>/dev/null
    echo -e "  ✅ 已停止 (PID: $SIM_PIDS)"
else
    echo -e "  ⏭️  未在运行"
fi

# 2. 停止 AgentServer
echo -e "${GREEN}[2/3]${NC} 🧠 停止 AgentServer..."
AGENT_PIDS=$(pgrep -f "python api.py" 2>/dev/null)
if [ -n "$AGENT_PIDS" ]; then
    kill $AGENT_PIDS 2>/dev/null
    sleep 2
    # 如还没死，强制杀
    pkill -9 -f "python api.py" 2>/dev/null || true
    echo -e "  ✅ 已停止"
else
    echo -e "  ⏭️  未在运行"
fi

# 3. 取消 Flink 作业
echo -e "${GREEN}[3/3]${NC} ⚡ 取消 Flink 作业..."
FLINK_URL="http://127.0.0.1:8081"
if curl -s "$FLINK_URL/overview" > /dev/null 2>&1; then
    RUNNING_JOBS=$(curl -s "$FLINK_URL/jobs/overview" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for j in data.get('jobs', []):
        if j['state'] == 'RUNNING':
            print(j['jid'])
except: pass
" 2>/dev/null)

    if [ -n "$RUNNING_JOBS" ]; then
        for JID in $RUNNING_JOBS; do
            curl -s -X PATCH "$FLINK_URL/jobs/$JID?mode=cancel" > /dev/null 2>&1
            echo -e "  ✅ 已取消作业: ${JID:0:12}..."
        done
    else
        echo -e "  ⏭️  没有运行中的作业"
    fi
else
    echo -e "  ⏭️  Flink 不可达，跳过"
fi

# 确认
echo ""
echo "═══════════════════════════════════════════════"
REMAINING=""
pgrep -f "python api.py" > /dev/null 2>&1 && REMAINING="${REMAINING} AgentServer"
pgrep -f "sensor_simulator" > /dev/null 2>&1 && REMAINING="${REMAINING} Simulator"

if [ -z "$REMAINING" ]; then
    echo -e " ${GREEN}✅ 所有应用层服务已停止${NC}"
else
    echo -e " ⚠️  仍在运行: $REMAINING"
fi

echo ""
echo " 💡 如需停止 Docker 基础设施:"
echo "    cd $PROJECT_DIR && docker compose down"
echo ""
