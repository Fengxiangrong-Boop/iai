#!/bin/bash
# ============================================
# IAI Grafana 一键配置脚本
# 自动配置数据源 + 创建工业智能可视化大屏
# ============================================

GRAFANA_URL="http://127.0.0.1:3000"
GRAFANA_AUTH="admin:admin"

echo "🔧 [1/3] 配置 InfluxDB 数据源..."
curl -s -X POST "$GRAFANA_URL/api/datasources" \
  -u "$GRAFANA_AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "InfluxDB-IAI",
    "type": "influxdb",
    "access": "proxy",
    "url": "http://influxdb:8086",
    "database": "iai",
    "isDefault": true,
    "jsonData": {
      "httpMode": "GET"
    }
  }' | python3 -m json.tool 2>/dev/null || echo "  (可能已存在)"

echo ""
echo "🔧 [2/3] 配置 MySQL 数据源..."
curl -s -X POST "$GRAFANA_URL/api/datasources" \
  -u "$GRAFANA_AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "MySQL-IAI",
    "type": "mysql",
    "access": "proxy",
    "url": "mysql:3306",
    "database": "iai",
    "user": "root",
    "secureJsonData": {
      "password": "mysql@123"
    },
    "jsonData": {}
  }' | python3 -m json.tool 2>/dev/null || echo "  (可能已存在)"

echo ""
echo "🔧 [3/3] 创建工业智能可视化大屏..."
curl -s -X POST "$GRAFANA_URL/api/dashboards/db" \
  -u "$GRAFANA_AUTH" \
  -H "Content-Type: application/json" \
  -d @- << 'DASHBOARD_EOF'
{
  "dashboard": {
    "id": null,
    "uid": "iai-realtime-dashboard",
    "title": "🏭 IAI 工业智能实时监控大屏",
    "tags": ["iai", "iiot", "realtime"],
    "timezone": "browser",
    "refresh": "10s",
    "time": {
      "from": "now-1h",
      "to": "now"
    },
    "panels": [
      {
        "id": 1,
        "title": "🌡️ 设备实时温度曲线",
        "type": "timeseries",
        "gridPos": {"h": 10, "w": 12, "x": 0, "y": 0},
        "datasource": {"type": "influxdb", "uid": null},
        "targets": [
          {
            "alias": "$tag_device_id",
            "query": "SELECT mean(\"temperature\") FROM \"sensor_raw\" WHERE $timeFilter GROUP BY time($__interval), \"device_id\" fill(null)",
            "rawQuery": true,
            "resultFormat": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "palette-classic"},
            "custom": {
              "lineWidth": 2,
              "fillOpacity": 10,
              "gradientMode": "scheme",
              "showPoints": "auto",
              "pointSize": 5
            },
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"color": "green", "value": null},
                {"color": "yellow", "value": 55},
                {"color": "red", "value": 65}
              ]
            },
            "unit": "celsius"
          }
        },
        "options": {
          "legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max"]},
          "tooltip": {"mode": "multi"}
        }
      },
      {
        "id": 2,
        "title": "📳 设备实时震动曲线",
        "type": "timeseries",
        "gridPos": {"h": 10, "w": 12, "x": 12, "y": 0},
        "datasource": {"type": "influxdb", "uid": null},
        "targets": [
          {
            "alias": "$tag_device_id",
            "query": "SELECT mean(\"vibration\") FROM \"sensor_raw\" WHERE $timeFilter GROUP BY time($__interval), \"device_id\" fill(null)",
            "rawQuery": true,
            "resultFormat": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "palette-classic"},
            "custom": {
              "lineWidth": 2,
              "fillOpacity": 10,
              "gradientMode": "scheme",
              "showPoints": "auto",
              "pointSize": 5
            },
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"color": "green", "value": null},
                {"color": "yellow", "value": 1.0},
                {"color": "red", "value": 1.2}
              ]
            },
            "unit": "accG"
          }
        },
        "options": {
          "legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max"]},
          "tooltip": {"mode": "multi"}
        }
      },
      {
        "id": 3,
        "title": "🔴 当前温度 (仪表盘)",
        "type": "gauge",
        "gridPos": {"h": 8, "w": 6, "x": 0, "y": 10},
        "datasource": {"type": "influxdb", "uid": null},
        "targets": [
          {
            "query": "SELECT last(\"temperature\") FROM \"sensor_raw\" WHERE $timeFilter GROUP BY \"device_id\"",
            "rawQuery": true,
            "resultFormat": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "min": 0, "max": 120,
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"color": "green", "value": null},
                {"color": "yellow", "value": 55},
                {"color": "orange", "value": 65},
                {"color": "red", "value": 85}
              ]
            },
            "unit": "celsius"
          }
        }
      },
      {
        "id": 4,
        "title": "📳 当前震动 (仪表盘)",
        "type": "gauge",
        "gridPos": {"h": 8, "w": 6, "x": 6, "y": 10},
        "datasource": {"type": "influxdb", "uid": null},
        "targets": [
          {
            "query": "SELECT last(\"vibration\") FROM \"sensor_raw\" WHERE $timeFilter GROUP BY \"device_id\"",
            "rawQuery": true,
            "resultFormat": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "min": 0, "max": 6,
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"color": "green", "value": null},
                {"color": "yellow", "value": 1.0},
                {"color": "orange", "value": 1.2},
                {"color": "red", "value": 3.0}
              ]
            },
            "unit": "accG"
          }
        }
      },
      {
        "id": 5,
        "title": "🚨 告警记录 (最新20条)",
        "type": "table",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 10},
        "datasource": {"type": "mysql", "uid": null},
        "targets": [
          {
            "rawSql": "SELECT created_at as time, trace_id, device_id, alert_level, temperature, vibration FROM alert_log ORDER BY created_at DESC LIMIT 20",
            "format": "table"
          }
        ],
        "fieldConfig": {
          "defaults": {},
          "overrides": [
            {
              "matcher": {"id": "byName", "options": "alert_level"},
              "properties": [
                {"id": "custom.cellOptions", "value": {"type": "color-text"}},
                {"id": "mappings", "value": [
                  {"type": "value", "options": {"P0": {"color": "red", "text": "🔴 P0"}, "P1": {"color": "orange", "text": "🟠 P1"}, "P2": {"color": "yellow", "text": "🟡 P2"}}}
                ]}
              ]
            }
          ]
        }
      },
      {
        "id": 6,
        "title": "📋 工单记录 (最新10条)",
        "type": "table",
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": 18},
        "datasource": {"type": "mysql", "uid": null},
        "targets": [
          {
            "rawSql": "SELECT created_at as time, order_id, device_id, priority, status, recommended_action FROM work_order ORDER BY created_at DESC LIMIT 10",
            "format": "table"
          }
        ]
      }
    ],
    "schemaVersion": 39,
    "version": 0
  },
  "overwrite": true
}
DASHBOARD_EOF

echo ""
echo "✅ Grafana 配置完成！"
echo "🌐 访问: http://192.168.0.105:3000"
echo "🔐 默认账号: admin / admin"
echo "📊 大屏: IAI 工业智能实时监控大屏"
