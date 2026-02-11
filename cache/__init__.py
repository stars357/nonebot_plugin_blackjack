# 缓存模块
import threading
import time
from typing import Dict, Any, Tuple

# 缓存过期时间（秒）
CACHE_EXPIRY = 300

# 缓存锁
cache_lock = threading.Lock()

# 缓存管理类
class CacheManager:
    def __init__(self):
        self.caches = {}
    
    def get_cache(self, cache_name: str) -> Dict:
        """获取指定名称的缓存字典"""
        if cache_name not in self.caches:
            self.caches[cache_name] = {}
        return self.caches[cache_name]
    
    def clear_cache(self, cache_name: str) -> None:
        """清空指定名称的缓存"""
        with cache_lock:
            if cache_name in self.caches:
                self.caches[cache_name].clear()
    
    def clear_all_caches(self) -> None:
        """清空所有缓存"""
        with cache_lock:
            for cache_name in self.caches:
                self.caches[cache_name].clear()
    
    def get_cached_value(self, cache_name: str, key: Any) -> Tuple[bool, Any]:
        """获取缓存值，返回(是否命中, 值)"""
        with cache_lock:
            cache = self.get_cache(cache_name)
            if key in cache:
                value, timestamp = cache[key]
                if time.time() - timestamp < CACHE_EXPIRY:
                    return True, value
                else:
                    # 缓存过期，删除
                    del cache[key]
                    return False, None
            return False, None
    
    def set_cached_value(self, cache_name: str, key: Any, value: Any) -> None:
        """设置缓存值"""
        with cache_lock:
            cache = self.get_cache(cache_name)
            cache[key] = (value, time.time())

# 创建全局缓存管理器
cache_manager = CacheManager()