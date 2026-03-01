"""
IAI Web 管理后台 API

提供告警记录、诊断报告、工单查询的 RESTful 接口，
以及一个内嵌的单页管理界面。

接口:
- GET /api/v1/dashboard/stats    → 系统统计概览
- GET /api/v1/dashboard/alerts   → 告警列表（分页）
- GET /api/v1/dashboard/orders   → 工单列表（分页）
- GET /dashboard                 → Web 管理界面
"""

from fastapi import APIRouter, Query, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from models.database import get_db
from services.event_bus import event_bus
import asyncio

router = APIRouter()

@router.get("/api/v1/dashboard/stream")
async def stream_logs(request: Request):
    """服务器推送技术 (SSE)，实时传输 Agent 系统日志"""
    async def event_generator():
        q = event_bus.subscribe("global_stream")
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe("global_stream", q)
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/api/v1/dashboard/stats")
def get_stats(db: Session = Depends(get_db)):
    """获取系统统计概览：告警总数、工单总数、各级别分布。"""
    try:
        alert_count = db.execute(text("SELECT COUNT(*) as cnt FROM alert_log")).scalar() or 0
        order_count = db.execute(text("SELECT COUNT(*) as cnt FROM work_order")).scalar() or 0

        # 告警级别分布
        level_rows = db.execute(text(
            "SELECT alert_level, COUNT(*) as cnt FROM alert_log GROUP BY alert_level"
        )).fetchall()
        level_dist = {row._mapping["alert_level"]: row._mapping["cnt"] for row in level_rows}

        # 工单状态分布
        status_rows = db.execute(text(
            "SELECT status, COUNT(*) as cnt FROM work_order GROUP BY status"
        )).fetchall()
        status_dist = {row._mapping["status"]: row._mapping["cnt"] for row in status_rows}

        return {
            "alert_total": alert_count,
            "order_total": order_count,
            "alert_level_distribution": level_dist,
            "order_status_distribution": status_dist,
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/v1/dashboard/alerts")
def get_alerts(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    """获取告警列表（分页），按时间倒序。"""
    try:
        offset = (page - 1) * size
        rows = db.execute(text(
            "SELECT trace_id, device_id, alert_level, temperature, vibration, created_at "
            "FROM alert_log ORDER BY created_at DESC LIMIT :size OFFSET :offset"
        ), {"size": size, "offset": offset}).fetchall()

        total = db.execute(text("SELECT COUNT(*) FROM alert_log")).scalar() or 0

        alerts = []
        for r in rows:
            d = dict(r._mapping)
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    val = v.isoformat()
                    d[k] = val + "Z" if getattr(v, "tzinfo", None) is None and not val.endswith("Z") else val
                elif hasattr(v, "normalize"):
                    d[k] = float(v)
            alerts.append(d)

        return {"total": total, "page": page, "size": size, "data": alerts}
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/v1/dashboard/orders")
def get_orders(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    """获取工单列表（分页），按时间倒序。"""
    try:
        offset = (page - 1) * size
        rows = db.execute(text(
            "SELECT order_id, device_id, priority, status, recommended_action, created_at "
            "FROM work_order ORDER BY created_at DESC LIMIT :size OFFSET :offset"
        ), {"size": size, "offset": offset}).fetchall()

        total = db.execute(text("SELECT COUNT(*) FROM work_order")).scalar() or 0

        orders = []
        for r in rows:
            d = dict(r._mapping)
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    val = v.isoformat()
                    d[k] = val + "Z" if getattr(v, "tzinfo", None) is None and not val.endswith("Z") else val
            orders.append(d)

        return {"total": total, "page": page, "size": size, "data": orders}
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/v1/dashboard/report/{trace_id}")
def get_report(trace_id: str, db: Session = Depends(get_db)):
    """获取指定告警的 AI 诊断报告。"""
    try:
        row = db.execute(text(
            "SELECT trace_id, device_id, diagnosis_text, decision_text, fault_category, severity, "
            "recommended_action, created_at "
            "FROM diagnosis_report WHERE trace_id = :trace_id LIMIT 1"
        ), {"trace_id": trace_id}).fetchone()

        if not row:
            return {"error": "诊断报告尚未生成或不存在"}

        d = dict(row._mapping)
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                val = v.isoformat()
                d[k] = val + "Z" if getattr(v, "tzinfo", None) is None and not val.endswith("Z") else val
        return d
    except Exception as e:
        return {"error": str(e)}


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    """内嵌的单页 Web 管理界面。"""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IAI 工业智能管理后台</title>
<style>
  :root {
    --bg: #0f172a; --card: #1e293b; --border: #334155;
    --text: #e2e8f0; --text-muted: #94a3b8;
    --accent: #38bdf8; --danger: #ef4444; --warning: #f59e0b; --success: #22c55e;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg); color: var(--text); min-height: 100vh;
  }
  .header {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border-bottom: 1px solid var(--border);
    padding: 16px 32px;
    display: flex; align-items: center; gap: 16px;
  }
  .header h1 { font-size: 22px; font-weight: 700; }
  .header h1 span { color: var(--accent); }
  .header .badge {
    background: var(--accent); color: #0f172a; font-size: 11px;
    padding: 3px 10px; border-radius: 12px; font-weight: 600;
  }
  .container { max-width: 1400px; margin: 0 auto; padding: 24px; }

  .stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
  .stat-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px; text-align: center; transition: transform 0.2s;
  }
  .stat-card:hover { transform: translateY(-2px); }
  .stat-card .number { font-size: 36px; font-weight: 800; }
  .stat-card .label { font-size: 13px; color: var(--text-muted); margin-top: 4px; }
  .stat-card.accent .number { color: var(--accent); }
  .stat-card.danger .number { color: var(--danger); }
  .stat-card.warning .number { color: var(--warning); }
  .stat-card.success .number { color: var(--success); }

  .tabs {
    display: flex; gap: 0; margin-bottom: 0; background: var(--card);
    border-radius: 12px 12px 0 0; border: 1px solid var(--border); border-bottom: none;
  }
  .tab {
    padding: 14px 28px; cursor: pointer; font-size: 14px; font-weight: 600;
    color: var(--text-muted); transition: all 0.2s; border-bottom: 3px solid transparent;
  }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }

  .table-wrap {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 0 0 12px 12px; overflow: hidden;
  }
  table { width: 100%; border-collapse: collapse; }
  th {
    text-align: left; padding: 12px 16px; font-size: 12px; text-transform: uppercase;
    letter-spacing: 0.5px; color: var(--text-muted); background: #111827;
    border-bottom: 1px solid var(--border);
  }
  td { padding: 12px 16px; font-size: 13px; border-bottom: 1px solid #1e293b; }
  tr:hover { background: rgba(56, 189, 248, 0.05); }

  .badge-level {
    padding: 3px 10px; border-radius: 6px; font-size: 11px; font-weight: 700;
  }
  .badge-P0 { background: rgba(239,68,68,0.2); color: #ef4444; }
  .badge-P1 { background: rgba(245,158,11,0.2); color: #f59e0b; }
  .badge-P2 { background: rgba(34,197,94,0.2); color: #22c55e; }
  .badge-status {
    padding: 3px 10px; border-radius: 6px; font-size: 11px; font-weight: 700;
  }
  .badge-PENDING { background: rgba(245,158,11,0.2); color: #f59e0b; }
  .badge-COMPLETED { background: rgba(34,197,94,0.2); color: #22c55e; }

  .pagination {
    display: flex; justify-content: center; gap: 8px; padding: 16px;
  }
  .pagination button {
    background: var(--border); border: none; color: var(--text);
    padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 13px;
  }
  .pagination button:hover { background: var(--accent); color: #0f172a; }
  .pagination button:disabled { opacity: 0.3; cursor: not-allowed; }
  .pagination span { padding: 8px 12px; font-size: 13px; color: var(--text-muted); }

  .loading { text-align: center; padding: 40px; color: var(--text-muted); }
  .action-text { max-width: 400px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  /* 弹窗样式 */
  .modal-overlay {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(4px);
    display: flex; align-items: center; justify-content: center;
    z-index: 1000; opacity: 0; pointer-events: none; transition: opacity 0.2s;
  }
  .modal-overlay.active { opacity: 1; pointer-events: auto; }
  .modal {
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    width: 90%; max-width: 800px; max-height: 90vh; display: flex; flex-direction: column;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
  }
  .modal-header {
    padding: 16px 24px; border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; align-items: center;
  }
  .modal-header h2 { font-size: 18px; margin: 0; }
  .modal-header .close {
    cursor: pointer; color: var(--text-muted); font-size: 24px; line-height: 1;
  }
  .modal-header .close:hover { color: var(--text); }
  .modal-body {
    padding: 24px; overflow-y: auto; line-height: 1.6; font-size: 14px;
    white-space: pre-wrap; word-wrap: break-word; font-family: 'Segoe UI', system-ui;
  }
  .modal-body h4 { margin-top: 16px; margin-bottom: 8px; color: var(--accent); }
  .modal-body .diag-box {
    background: rgba(0,0,0,0.2); padding: 16px; border-radius: 8px; border: 1px dashed var(--border); margin-bottom: 16px;
  }
  
  .btn {
    background: transparent; border: 1px solid var(--accent); color: var(--accent);
    padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 12px; transition: all 0.2s;
  }
  .btn:hover { background: var(--accent); color: #0f172a; }

  /* 悬浮实时终端 */
  .terminal-panel {
    background: #0a0e17; border: 1px solid var(--border); border-radius: 12px;
    margin-top: 24px; display: flex; flex-direction: column; overflow: hidden;
  }
  .terminal-header {
    background: #111827; padding: 12px 16px; font-size: 13px; font-weight: bold;
    color: var(--accent); border-bottom: 1px solid var(--border);
  }
  .terminal-body {
    padding: 16px; height: 300px; overflow-y: auto;
    font-family: 'JetBrains Mono', 'Courier New', monospace; font-size: 13px;
    line-height: 1.6; color: #a3be8c;
  }
  .log-line { margin-bottom: 4px; border-bottom: 1px dashed rgba(255,255,255,0.05); padding-bottom: 4px;}
  .log-line b { color: #88c0d0; }

  @media (max-width: 768px) {
    .stats-row { grid-template-columns: repeat(2, 1fr); }
  }
</style>
</head>
<body>

<div class="header">
  <h1>🏭 <span>IAI</span> 工业智能管理后台</h1>
  <span class="badge">v1.0.0</span>
</div>

<div class="container">
  <div class="stats-row" id="stats-row">
    <div class="stat-card accent"><div class="number" id="stat-alerts">-</div><div class="label">告警总数</div></div>
    <div class="stat-card danger"><div class="number" id="stat-p0">-</div><div class="label">P0 紧急告警</div></div>
    <div class="stat-card warning"><div class="number" id="stat-p1">-</div><div class="label">P1 高优告警</div></div>
    <div class="stat-card success"><div class="number" id="stat-orders">-</div><div class="label">工单总数</div></div>
  </div>

  <div class="tabs">
    <div class="tab active" onclick="switchTab('alerts')">🚨 告警记录</div>
    <div class="tab" onclick="switchTab('orders')">📋 工单管理</div>
  </div>

  <div class="table-wrap">
    <div id="table-content"><div class="loading">加载中...</div></div>
    <div class="pagination" id="pagination"></div>
  </div>

  <div class="terminal-panel" id="terminalPanel">
    <div class="terminal-header"><span style="display:inline-block;width:8px;height:8px;background:#22c55e;border-radius:50%;margin-right:8px;animation:blink 1.5s infinite;"></span> AI 大脑实时思维网段 (全局溯源)</div>
    <div class="terminal-body" id="terminalBody">
      <div style="color:var(--text-muted)">>>> 正在监听系统突发事件大模型推演实况...</div>
    </div>
  </div>
  <style>@keyframes blink { 0% {opacity:1;} 50% {opacity:0.3;} 100% {opacity:1;} }</style>
</div>

<!-- 诊断报告弹窗 -->
<div class="modal-overlay" id="reportModal" onclick="if(event.target===this) closeModal()">
  <div class="modal">
    <div class="modal-header">
      <h2 id="modalTitle">🔍 AI 诊断报告</h2>
      <span class="close" onclick="closeModal()">&times;</span>
    </div>
    <div class="modal-body" id="modalBody">加载中...</div>
  </div>
</div>

<script>
let currentTab = 'alerts';
let currentPage = 1;

async function loadStats() {
  try {
    const res = await fetch('/api/v1/dashboard/stats');
    const d = await res.json();
    document.getElementById('stat-alerts').textContent = d.alert_total || 0;
    document.getElementById('stat-orders').textContent = d.order_total || 0;
    document.getElementById('stat-p0').textContent = (d.alert_level_distribution || {})['P0'] || 0;
    document.getElementById('stat-p1').textContent = (d.alert_level_distribution || {})['P1'] || 0;
  } catch(e) { console.error(e); }
}

async function loadTable(tab, page) {
  currentTab = tab; currentPage = page;
  const url = tab === 'alerts'
    ? `/api/v1/dashboard/alerts?page=${page}&size=15`
    : `/api/v1/dashboard/orders?page=${page}&size=15`;
  try {
    const res = await fetch(url);
    const d = await res.json();
    if (d.error) { document.getElementById('table-content').innerHTML = `<div class="loading">${d.error}</div>`; return; }

    let html = '<table><thead><tr>';
    if (tab === 'alerts') {
      html += '<th>时间</th><th>设备</th><th>级别</th><th>温度</th><th>震动</th><th>Trace ID</th><th>操作</th>';
    } else {
      html += '<th>时间</th><th>工单号</th><th>设备</th><th>优先级</th><th>状态</th><th>建议操作</th><th>操作</th>';
    }
    html += '</tr></thead><tbody>';

    for (const row of d.data) {
      if (tab === 'alerts') {
        const lvl = row.alert_level || 'P2';
        html += `<tr>
          <td>${formatTime(row.created_at)}</td>
          <td><strong>${row.device_id}</strong></td>
          <td><span class="badge-level badge-${lvl}">${lvl}</span></td>
          <td>${row.temperature ? row.temperature + '°C' : '-'}</td>
          <td>${row.vibration ? row.vibration + 'G' : '-'}</td>
          <td style="font-family:monospace;font-size:11px;color:var(--text-muted)">${(row.trace_id||'').slice(0,12)}...</td>
          <td><button class="btn" onclick="viewReport('${row.trace_id}', '${row.device_id}')">查看诊断</button></td>
        </tr>`;
      } else {
        const st = row.status || 'PENDING';
        html += `<tr>
          <td>${formatTime(row.created_at)}</td>
          <td style="font-family:monospace">${row.order_id || '-'}</td>
          <td><strong>${row.device_id}</strong></td>
          <td><span class="badge-level badge-${row.priority||'P1'}">${row.priority||'-'}</span></td>
          <td><span class="badge-status badge-${st}">${st}</span></td>
          <td class="action-text" title="${(row.recommended_action||'').replace(/"/g,'&quot;')}">${row.recommended_action || '-'}</td>
          <td><button class="btn" onclick="viewReport('${row.trace_id}', '${row.device_id}')">查看诊断</button></td>
        </tr>`;
      }
    }
    html += '</tbody></table>';
    document.getElementById('table-content').innerHTML = html;

    // 分页
    const totalPages = Math.ceil(d.total / d.size) || 1;
    let pgHtml = `<button ${page<=1?'disabled':''} onclick="loadTable('${tab}',${page-1})">上一页</button>`;
    pgHtml += `<span>第 ${page} / ${totalPages} 页 (共 ${d.total} 条)</span>`;
    pgHtml += `<button ${page>=totalPages?'disabled':''} onclick="loadTable('${tab}',${page+1})">下一页</button>`;
    document.getElementById('pagination').innerHTML = pgHtml;
  } catch(e) {
    document.getElementById('table-content').innerHTML = `<div class="loading">加载失败: ${e.message}</div>`;
  }
}

async function viewReport(traceId, deviceId) {
  if (!traceId || traceId === 'null') {
    alert("该记录没有关联的诊断流水号 (Trace ID)");
    return;
  }
  document.getElementById('reportModal').classList.add('active');
  document.getElementById('modalTitle').textContent = `🔍 AI 诊断报告 - ${deviceId}`;
  document.getElementById('modalBody').innerHTML = `<div class="loading">正在从知识库调取大模型诊断记录...</div>`;
  
  try {
    const res = await fetch(`/api/v1/dashboard/report/${traceId}`);
    const d = await res.json();
    
    if (d.error) {
      document.getElementById('modalBody').innerHTML = `<div style="color:var(--danger)">${d.error}</div>`;
      return;
    }
    
    let reportHtml = `
      <div style="font-size:12px;color:var(--text-muted);margin-bottom:16px;">
        诊断时间: ${formatTime(d.created_at)} | 故障分级: <span class="badge-level badge-${d.severity || 'P1'}">${d.severity || '未知'}</span>
      </div>
      <h4>👨‍⚕️ 诊断专家分析报告</h4>
      <div class="diag-box">${escapeHtml(d.diagnosis_text || '无详细分析记录')}</div>
      
      <h4>👨‍⚖️ 决策专家建议方案</h4>
      <div class="diag-box" style="border-color:var(--success)">${escapeHtml(d.decision_text || '暂无决策建议')}</div>
    `;
    document.getElementById('modalBody').innerHTML = reportHtml;
  } catch(e) {
    document.getElementById('modalBody').innerHTML = `<div style="color:var(--danger)">加载报告失败: ${e.message}</div>`;
  }
}

function closeModal() {
  document.getElementById('reportModal').classList.remove('active');
}

function escapeHtml(unsafe) {
    return (unsafe||'').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function formatTime(isoStr) {
  if (!isoStr) return '-';
  const d = new Date(isoStr);
  if (isNaN(d)) return isoStr;
  return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0') + ' ' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0') + ':' + String(d.getSeconds()).padStart(2, '0');
}

function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
  loadTable(tab, 1);
}

// 连接 SSE 事件流
const eventSource = new EventSource('/api/v1/dashboard/stream');
eventSource.onmessage = function(event) {
  const terminal = document.getElementById('terminalBody');
  const div = document.createElement('div');
  div.className = 'log-line';
  div.innerHTML = event.data;
  terminal.appendChild(div);
  // 保持滚动条在最底部
  terminal.scrollTop = terminal.scrollHeight;
};

// 初始化
loadStats();
loadTable('alerts', 1);
// 每 30 秒自动刷新
setInterval(() => { loadStats(); loadTable(currentTab, currentPage); }, 30000);
</script>
</body>
</html>"""
