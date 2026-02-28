"""
Nacos 服务注册与心跳模块

功能:
- 服务启动时自动注册到 Nacos
- 后台线程定时发送心跳（每 5 秒）
- 服务关闭时自动注销

输入: service_name, ip, port, nacos_url
输出: 注册成功/失败日志

注意: 如果 Nacos 不可用，服务仍可正常运行（fail-open）
"""

import os
import threading
import time
import requests
from logger import logger

NACOS_URL = os.getenv("NACOS_URL", "http://192.168.0.105:8848")
SERVICE_NAME = os.getenv("SERVICE_NAME", "agent-server")
SERVICE_IP = os.getenv("SERVICE_IP", "192.168.0.105")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8000"))

# 禁用代理，确保 Nacos 请求直连（避免走系统代理导致超时）
NO_PROXY = {"http": None, "https": None}


def register_to_nacos() -> bool:
    """
    向 Nacos 注册当前服务实例。
    
    返回: True 注册成功, False 注册失败
    """
    try:
        url = f"{NACOS_URL}/nacos/v1/ns/instance"
        params = {
            "serviceName": SERVICE_NAME,
            "ip": SERVICE_IP,
            "port": SERVICE_PORT,
            "healthy": "true",
            "weight": "1.0",
            "metadata": '{"version":"1.0.0","framework":"fastapi"}'
        }
        resp = requests.post(url, params=params, timeout=5, proxies=NO_PROXY)
        if resp.status_code == 200 and resp.text == "ok":
            logger.info(f"✅ [Nacos] 服务 '{SERVICE_NAME}' 注册成功 ({SERVICE_IP}:{SERVICE_PORT})")
            return True
        else:
            logger.warning(f"⚠️ [Nacos] 注册返回异常: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        logger.warning(f"⚠️ [Nacos] 注册失败(服务仍可正常运行): {e}")
        return False


def deregister_from_nacos():
    """向 Nacos 注销当前服务实例。"""
    try:
        url = f"{NACOS_URL}/nacos/v1/ns/instance"
        params = {
            "serviceName": SERVICE_NAME,
            "ip": SERVICE_IP,
            "port": SERVICE_PORT,
        }
        resp = requests.delete(url, params=params, timeout=5, proxies=NO_PROXY)
        logger.info(f"🛑 [Nacos] 服务 '{SERVICE_NAME}' 已注销: {resp.text}")
    except Exception as e:
        logger.warning(f"⚠️ [Nacos] 注销失败: {e}")


def _heartbeat_loop(stop_event: threading.Event):
    """
    心跳线程：每 5 秒向 Nacos 发送一次心跳，保持服务实例存活。
    """
    while not stop_event.is_set():
        try:
            url = f"{NACOS_URL}/nacos/v1/ns/instance/beat"
            params = {
                "serviceName": SERVICE_NAME,
                "ip": SERVICE_IP,
                "port": SERVICE_PORT,
            }
            resp = requests.put(url, params=params, timeout=5, proxies=NO_PROXY)
            if resp.status_code != 200:
                logger.debug(f"[Nacos] 心跳返回: {resp.status_code}")
        except Exception:
            pass  # 心跳失败不影响业务, 静默处理
        stop_event.wait(5)  # 每 5 秒一次


# 心跳线程控制
_heartbeat_stop = threading.Event()
_heartbeat_thread = None


def start_heartbeat():
    """启动后台心跳线程。"""
    global _heartbeat_thread
    _heartbeat_stop.clear()
    _heartbeat_thread = threading.Thread(target=_heartbeat_loop, args=(_heartbeat_stop,), daemon=True)
    _heartbeat_thread.start()
    logger.info("💓 [Nacos] 心跳线程已启动 (间隔 5s)")


def stop_heartbeat():
    """停止后台心跳线程。"""
    _heartbeat_stop.set()
    if _heartbeat_thread:
        _heartbeat_thread.join(timeout=3)
    logger.info("💔 [Nacos] 心跳线程已停止")
