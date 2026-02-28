import os
import requests
import json
from logger import logger

NACOS_URL = os.getenv("NACOS_URL", "http://192.168.0.105:8848")
NAMESPACE_ID = ""

# 禁用代理，确保 Nacos 请求直连
NO_PROXY = {"http": None, "https": None}

class NacosConfigManager:
    _cache = {}

    @classmethod
    def get_config(cls, data_id, group="DEFAULT_GROUP", default_val=None):
        """
        从 Nacos 动态获取配置内容。
        如果获取失败，则返回上次缓存的成功版本或指定的默认值。
        """
        try:
            url = f"{NACOS_URL}/nacos/v1/cs/configs"
            params = {
                "tenant": NAMESPACE_ID,
                "dataId": data_id,
                "group": group
            }
            resp = requests.get(url, params=params, timeout=3, proxies=NO_PROXY)
            if resp.status_code == 200:
                cls._cache[data_id] = resp.text
                return resp.text
            else:
                logger.debug(f"[Nacos] 找不到配置 {data_id}，使用默认值")
        except Exception as e:
            logger.warning(f"⚠️ [Nacos] 配置请求异常 {data_id}: {e}")
        
        return cls._cache.get(data_id, default_val)

    @classmethod
    def get_json_config(cls, data_id, group="DEFAULT_GROUP", default_val=None):
        """获取 JSON 格式配置并解析为 dict"""
        text = cls.get_config(data_id, group, None)
        if text:
            try:
                return json.loads(text)
            except Exception as e:
                logger.warning(f"⚠️ [Nacos] 配置 {data_id} JSON 解析失败: {e}")
        return default_val
