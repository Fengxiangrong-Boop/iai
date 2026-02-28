#!/bin/bash
# ============================================
# IAI 工业智能体系统 - 全栈停止脚本
# ============================================
# 用法:
#   bash stop_all.sh              # 停止应用服务（保留 Docker 基础设施）
#   bash stop_all.sh --all        # 停止全部（包括 Docker 基础设施）
# ============================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   🛑 IAI 工业智能体系统 - 全栈停止          ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ========================================
# 1. 停止传感器模拟器（优先停止，减少 API 消耗）
# ========================================
echo -e "${GREEN}[1/4]${NC} 📡 停止传感器模拟器..."
SIM_PIDS=$(pgrep -f "sensor_simulator" 2>/dev/null)
if [ -n "$SIM_PIDS" ]; then
    kill $SIM_PIDS 2>/dev/null
    echo -e "  ${GREEN}✅${NC} 已停止 (PID: $SIM_PIDS)"
else
    echo -e "  ⏭️  未在运行"
fi

# ========================================
# 2. 停止 AgentServer
# ========================================
echo -e "${GREEN}[2/4]${NC} 🧠 停止 AgentServer..."
AGENT_PIDS=$(pgrep -f "python api.py" 2>/dev/null)
if [ -n "$AGENT_PIDS" ]; then
    kill $AGENT_PIDS 2>/dev/null
    echo -e "  ${GREEN}✅${NC} 已停止 (PID: $AGENT_PIDS)"
else
    echo -e "  ⏭️  未在运行"
fi

# ========================================
# 3. 取消 Flink 作业
# ========================================
echo -e "${GREEN}[3/4]${NC} ⚡ 取消 Flink 作业..."
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
            echo -e "  ${GREEN}✅${NC} 已取消作业: $JID"
        done
    else
        echo -e "  ⏭️  没有正在运行的作业"
    fi
else
    echo -e "  ${YELLOW}⚠️${NC}  Flink 不可达，跳过"
fi

# ========================================
# 4. 停止 Docker 基础设施（可选）
# ========================================
echo -e "${GREEN}[4/4]${NC} 🐳 Docker 基础设施..."
if [ "$1" = "--all" ]; then
    echo "  正在停止所有 Docker 容器..."
    cd "$PROJECT_DIR"
    docker-compose down 2>/dev/null || docker compose down 2>/dev/null || true
    echo -e "  ${GREEN}✅${NC} Docker 基础设施已停止"
else
    echo -e "  ⏭️  保留运行（如需停止请加 ${YELLOW}--all${NC} 参数）"
fi

# ========================================
# 确认状态
# ========================================
echo ""
echo "═══════════════════════════════════════════════"
echo "📋 进程检查:"

# 检查关键进程
REMAINING=""
pgrep -f "python api.py" > /dev/null 2>&1 && REMAINING="${REMAINING} AgentServer"
pgrep -f "sensor_simulator" > /dev/null 2>&1 && REMAINING="${REMAINING} Simulator"

if [ -z "$REMAINING" ]; then
    echo -e "  ${GREEN}✅ 所有应用进程已停止${NC}"
else
    echo -e "  ${RED}⚠️  仍在运行:${REMAINING}${NC}"
fi

echo ""
echo -e "💰 ${GREEN}大模型 API 不会再被调用，钱包安全！${NC}"
echo ""
