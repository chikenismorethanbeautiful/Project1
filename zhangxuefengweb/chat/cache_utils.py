# cache_utils.py - 修复 UUID 序列化问题

import json
import os
from datetime import datetime, timedelta
from django.conf import settings
from uuid import UUID


class UUIDEncoder(json.JSONEncoder):
    """自定义 JSON 编码器，支持 UUID"""

    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class StatsCache:
    """统计数据缓存"""

    CACHE_DIR = os.path.join(settings.BASE_DIR, 'cache')

    @classmethod
    def _ensure_cache_dir(cls):
        """确保缓存目录存在"""
        if not os.path.exists(cls.CACHE_DIR):
            os.makedirs(cls.CACHE_DIR)

    @classmethod
    def _get_cache_path(cls, key):
        """获取缓存文件路径"""
        cls._ensure_cache_dir()
        return os.path.join(cls.CACHE_DIR, f'{key}.json')

    @classmethod
    def get(cls, key, max_age_minutes=30):
        """获取缓存，过期返回None"""
        cache_path = cls._get_cache_path(key)
        if not os.path.exists(cache_path):
            return None

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 检查是否过期
            cached_time = datetime.fromisoformat(data['cached_at'])
            if datetime.now() - cached_time > timedelta(minutes=max_age_minutes):
                return None

            return data['value']
        except (json.JSONDecodeError, KeyError, ValueError):
            # 缓存文件损坏，删除并返回None
            cls.delete(key)
            return None

    @classmethod
    def set(cls, key, value):
        """设置缓存"""
        cache_path = cls._get_cache_path(key)
        data = {
            'cached_at': datetime.now().isoformat(),
            'value': value
        }
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, cls=UUIDEncoder)

    @classmethod
    def delete(cls, key):
        """删除缓存"""
        cache_path = cls._get_cache_path(key)
        if os.path.exists(cache_path):
            os.remove(cache_path)

    @classmethod
    def clear_all(cls):
        """清空所有缓存"""
        if os.path.exists(cls.CACHE_DIR):
            for file in os.listdir(cls.CACHE_DIR):
                file_path = os.path.join(cls.CACHE_DIR, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)