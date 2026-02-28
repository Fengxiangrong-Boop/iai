#!/bin/bash
# ============================================
# IAI Grafana 大屏优化版 - 平滑清晰趋势曲线
# ============================================

GRAFANA_URL="http://127.0.0.1:3000"
GRAFANA_AUTH="admin:admin123"

echo "🎨 正在更新大屏样式..."
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
      "from": "now-30m",
      "to": "now"
    },
    "panels": [
      {
        "id": 1,
        "title": "🌡️ 设备温度趋势",
        "description": "30秒平滑聚合，清晰展示温度变化趋势",
        "type": "timeseries",
        "gridPos": {"h": 10, "w": 12, "x": 0, "y": 0},
        "datasource": {"type": "influxdb", "uid": null},
        "targets": [
          {
            "alias": "$tag_device_id",
            "query": "SELECT mean(\"temperature\") FROM \"sensor_raw\" WHERE $timeFilter GROUP BY time(30s), \"device_id\" fill(previous)",
            "rawQuery": true,
            "resultFormat": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "palette-classic"},
            "custom": {
              "lineWidth": 3,
              "fillOpacity": 8,
              "gradientMode": "opacity",
              "lineInterpolation": "smooth",
              "showPoints": "never",
              "spanNulls": true,
              "axisBorderShow": true,
              "barAlignment": 0,
              "drawStyle": "line",
              "lineStyle": {"fill": "solid"},
              "pointSize": 5,
              "scaleDistribution": {"type": "linear"},
              "stacking": {"mode": "none"}
            },
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"color": "green", "value": null},
                {"color": "#EAB839", "value": 55},
                {"color": "red", "value": 65}
              ]
            },
            "unit": "celsius",
            "min": 20
          }
        },
        "options": {
          "legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max", "last"]},
          "tooltip": {"mode": "multi", "sort": "desc"}
        }
      },
      {
        "id": 2,
        "title": "📳 设备震动趋势",
        "description": "30秒平滑聚合，清晰展示震动变化趋势",
        "type": "timeseries",
        "gridPos": {"h": 10, "w": 12, "x": 12, "y": 0},
        "datasource": {"type": "influxdb", "uid": null},
        "targets": [
          {
            "alias": "$tag_device_id",
            "query": "SELECT mean(\"vibration\") FROM \"sensor_raw\" WHERE $timeFilter GROUP BY time(30s), \"device_id\" fill(previous)",
            "rawQuery": true,
            "resultFormat": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "palette-classic"},
            "custom": {
              "lineWidth": 3,
              "fillOpacity": 8,
              "gradientMode": "opacity",
              "lineInterpolation": "smooth",
              "showPoints": "never",
              "spanNulls": true,
              "axisBorderShow": true,
              "drawStyle": "line",
              "lineStyle": {"fill": "solid"},
              "pointSize": 5,
              "scaleDistribution": {"type": "linear"},
              "stacking": {"mode": "none"}
            },
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"color": "green", "value": null},
                {"color": "#EAB839", "value": 1.0},
                {"color": "red", "value": 1.2}
              ]
            },
            "unit": "accG",
            "min": 0,
            "decimals": 2
          }
        },
        "options": {
          "legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max", "last"]},
          "tooltip": {"mode": "multi", "sort": "desc"}
        }
      },
      {
        "id": 7,
        "title": "🌡️ 温度峰值追踪",
        "description": "每分钟最高温度",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 10},
        "datasource": {"type": "influxdb", "uid": null},
        "targets": [
          {
            "alias": "$tag_device_id 峰值",
            "query": "SELECT max(\"temperature\") FROM \"sensor_raw\" WHERE $timeFilter GROUP BY time(1m), \"device_id\" fill(previous)",
            "rawQuery": true,
            "resultFormat": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "palette-classic"},
            "custom": {
              "lineWidth": 2,
              "fillOpacity": 15,
              "gradientMode": "scheme",
              "lineInterpolation": "smooth",
              "showPoints": "auto",
              "pointSize": 6,
              "spanNulls": true,
              "drawStyle": "line",
              "stacking": {"mode": "none"},
              "thresholdsStyle": {"mode": "dashed"}
            },
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"color": "green", "value": null},
                {"color": "red", "value": 65}
              ]
            },
            "unit": "celsius",
            "min": 20
          }
        },
        "options": {
          "legend": {"displayMode": "list", "placement": "bottom"},
          "tooltip": {"mode": "multi"}
        }
      },
      {
        "id": 8,
        "title": "📳 震动峰值追踪",
        "description": "每分钟最高震动",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 10},
        "datasource": {"type": "influxdb", "uid": null},
        "targets": [
          {
            "alias": "$tag_device_id 峰值",
            "query": "SELECT max(\"vibration\") FROM \"sensor_raw\" WHERE $timeFilter GROUP BY time(1m), \"device_id\" fill(previous)",
            "rawQuery": true,
            "resultFormat": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "palette-classic"},
            "custom": {
              "lineWidth": 2,
              "fillOpacity": 15,
              "gradientMode": "scheme",
              "lineInterpolation": "smooth",
              "showPoints": "auto",
              "pointSize": 6,
              "spanNulls": true,
              "drawStyle": "line",
              "stacking": {"mode": "none"},
              "thresholdsStyle": {"mode": "dashed"}
            },
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"color": "green", "value": null},
                {"color": "red", "value": 1.2}
              ]
            },
            "unit": "accG",
            "min": 0,
            "decimals": 2
          }
        },
        "options": {
          "legend": {"displayMode": "list", "placement": "bottom"},
          "tooltip": {"mode": "multi"}
        }
      },
      {
        "id": 3,
        "title": "🔴 当前温度",
        "type": "gauge",
        "gridPos": {"h": 7, "w": 6, "x": 0, "y": 18},
        "datasource": {"type": "influxdb", "uid": null},
        "targets": [
          {
            "alias": "$tag_device_id",
            "query": "SELECT last(\"temperature\") FROM \"sensor_raw\" WHERE time > now() - 2m GROUP BY \"device_id\"",
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
                {"color": "#EAB839", "value": 55},
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
        "title": "📳 当前震动",
        "type": "gauge",
        "gridPos": {"h": 7, "w": 6, "x": 6, "y": 18},
        "datasource": {"type": "influxdb", "uid": null},
        "targets": [
          {
            "alias": "$tag_device_id",
            "query": "SELECT last(\"vibration\") FROM \"sensor_raw\" WHERE time > now() - 2m GROUP BY \"device_id\"",
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
                {"color": "#EAB839", "value": 1.0},
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
        "gridPos": {"h": 7, "w": 12, "x": 12, "y": 18},
        "datasource": {"type": "mysql", "uid": null},
        "targets": [
          {
            "rawSql": "SELECT created_at as time, device_id, alert_level, temperature, vibration FROM alert_log ORDER BY created_at DESC LIMIT 20",
            "format": "table"
          }
        ]
      },
      {
        "id": 6,
        "title": "📋 AI 工单记录",
        "type": "table",
        "gridPos": {"h": 7, "w": 24, "x": 0, "y": 25},
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
echo "✅ 大屏优化完成！"
echo "🌐 刷新页面查看: http://192.168.0.105:3000/d/iai-realtime-dashboard"
