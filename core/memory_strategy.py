# core/memory_strategy.py - 策略记忆系统，支持EMA健康度和TTL
from typing import Dict, Any, Optional, List, Tuple
import time
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

@dataclass
class StrategyMemory:
    """策略记忆条目"""
    strategy_id: str
    params_hash: str  # 参数组合的哈希值
    success_count: int = 0
    failure_count: int = 0
    ema_health: float = 0.5  # EMA健康度 [0,1]
    last_used_ts: float = field(default_factory=time.time)
    created_ts: float = field(default_factory=time.time)
    page_context: Dict[str, Any] = field(default_factory=dict)  # 页面上下文信息
    
    def total_attempts(self) -> int:
        return self.success_count + self.failure_count
    
    def raw_success_rate(self) -> float:
        total = self.total_attempts()
        return self.success_count / total if total > 0 else 0.0
    
    def is_healthy(self, threshold: float = 0.75) -> bool:
        return self.ema_health >= threshold
    
    def should_expire(self, ttl_seconds: int) -> bool:
        if ttl_seconds <= 0:
            return False
        return time.time() - self.last_used_ts > ttl_seconds

class StrategyMemoryStore:
    """策略记忆存储管理器"""
    
    def __init__(self, storage_path: str = "out/strategy_memory.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(exist_ok=True, parents=True)
        
        # 配置参数
        self.ema_alpha = float(os.getenv("STRATEGY_EMA_ALPHA", "0.3"))
        self.ttl_seconds = int(os.getenv("STRATEGY_CACHE_TTL_S", "3600"))
        self.health_threshold = float(os.getenv("STRATEGY_HEALTH_TH", "0.75"))
        
        # 内存缓存
        self._memory_cache: Dict[str, StrategyMemory] = {}
        self._load_from_disk()
    
    def _make_key(self, strategy_id: str, params_hash: str, page_kind: str = "") -> str:
        """生成记忆条目的唯一键"""
        return f"{strategy_id}:{params_hash}:{page_kind}"
    
    def _params_to_hash(self, params: Dict[str, Any]) -> str:
        """将参数字典转换为稳定的哈希值"""
        import hashlib
        normalized = json.dumps(params, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(normalized.encode()).hexdigest()[:12]
    
    def _load_from_disk(self):
        """从磁盘加载记忆数据"""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for key, entry_data in data.items():
                memory = StrategyMemory(**entry_data)
                self._memory_cache[key] = memory
                
        except Exception as e:
            print(f"[memory_strategy] Failed to load from {self.storage_path}: {e}")
    
    def _save_to_disk(self):
        """保存记忆数据到磁盘"""
        try:
            data = {}
            for key, memory in self._memory_cache.items():
                data[key] = asdict(memory)
            
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"[memory_strategy] Failed to save to {self.storage_path}: {e}")
    
    def _cleanup_expired(self):
        """清理过期的记忆条目"""
        if self.ttl_seconds <= 0:
            return
        
        expired_keys = []
        for key, memory in self._memory_cache.items():
            if memory.should_expire(self.ttl_seconds):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._memory_cache[key]
        
        if expired_keys:
            print(f"[memory_strategy] Cleaned up {len(expired_keys)} expired entries")
    
    def get_memory(self, strategy_id: str, params: Dict[str, Any], 
                   page_kind: str = "") -> Optional[StrategyMemory]:
        """获取策略记忆"""
        self._cleanup_expired()
        
        params_hash = self._params_to_hash(params)
        key = self._make_key(strategy_id, params_hash, page_kind)
        
        return self._memory_cache.get(key)
    
    def record_outcome(self, strategy_id: str, params: Dict[str, Any], 
                       success: bool, page_context: Dict[str, Any] = None,
                       page_kind: str = ""):
        """记录策略执行结果并更新EMA健康度"""
        params_hash = self._params_to_hash(params)
        key = self._make_key(strategy_id, params_hash, page_kind)
        
        # 获取或创建记忆条目
        memory = self._memory_cache.get(key)
        if memory is None:
            memory = StrategyMemory(
                strategy_id=strategy_id,
                params_hash=params_hash,
                page_context=page_context or {}
            )
            self._memory_cache[key] = memory
        
        # 更新统计计数
        if success:
            memory.success_count += 1
        else:
            memory.failure_count += 1
        
        # 更新EMA健康度
        outcome_value = 1.0 if success else 0.0
        memory.ema_health = (1 - self.ema_alpha) * memory.ema_health + self.ema_alpha * outcome_value
        
        # 更新时间戳
        memory.last_used_ts = time.time()
        
        # 更新页面上下文（合并）
        if page_context:
            memory.page_context.update(page_context)
        
        # 持久化
        self._save_to_disk()
        
        print(f"[memory_strategy] Recorded {strategy_id} outcome={success} ema_health={memory.ema_health:.3f}")
    
    def get_healthy_strategies(self, page_kind: str = "") -> List[Tuple[str, Dict[str, Any], float]]:
        """获取健康的策略列表，返回(strategy_id, params, ema_health)"""
        self._cleanup_expired()
        
        healthy = []
        for key, memory in self._memory_cache.items():
            if not memory.is_healthy(self.health_threshold):
                continue
            
            # 检查页面类型匹配
            if page_kind and not key.endswith(f":{page_kind}"):
                continue
            
            # 重构参数字典
            try:
                params = json.loads(json.dumps(memory.page_context.get('last_params', {})))
                healthy.append((memory.strategy_id, params, memory.ema_health))
            except:
                continue
        
        # 按健康度排序
        healthy.sort(key=lambda x: x[2], reverse=True)
        return healthy
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """获取记忆系统统计信息"""
        self._cleanup_expired()
        
        total_entries = len(self._memory_cache)
        healthy_count = sum(1 for m in self._memory_cache.values() if m.is_healthy(self.health_threshold))
        
        if total_entries == 0:
            return {
                "total_entries": 0,
                "healthy_count": 0,
                "avg_health": 0.0,
                "strategies": {}
            }
        
        avg_health = sum(m.ema_health for m in self._memory_cache.values()) / total_entries
        
        # 按策略ID统计
        strategy_stats = {}
        for memory in self._memory_cache.values():
            sid = memory.strategy_id
            if sid not in strategy_stats:
                strategy_stats[sid] = {
                    "count": 0,
                    "avg_health": 0.0,
                    "total_attempts": 0
                }
            
            stats = strategy_stats[sid]
            stats["count"] += 1
            stats["avg_health"] += memory.ema_health
            stats["total_attempts"] += memory.total_attempts()
        
        # 计算平均值
        for sid, stats in strategy_stats.items():
            if stats["count"] > 0:
                stats["avg_health"] /= stats["count"]
        
        return {
            "total_entries": total_entries,
            "healthy_count": healthy_count,
            "avg_health": avg_health,
            "ttl_seconds": self.ttl_seconds,
            "health_threshold": self.health_threshold,
            "strategies": strategy_stats
        }
    
    def reset_memory(self, strategy_id: str = None):
        """重置记忆（可选择特定策略）"""
        if strategy_id is None:
            self._memory_cache.clear()
            print("[memory_strategy] Reset all memory")
        else:
            keys_to_remove = [k for k, m in self._memory_cache.items() if m.strategy_id == strategy_id]
            for key in keys_to_remove:
                del self._memory_cache[key]
            print(f"[memory_strategy] Reset memory for strategy {strategy_id}, removed {len(keys_to_remove)} entries")
        
        self._save_to_disk()

# 全局单例
_global_memory_store = None

def get_memory_store() -> StrategyMemoryStore:
    """获取全局记忆存储实例"""
    global _global_memory_store
    if _global_memory_store is None:
        _global_memory_store = StrategyMemoryStore()
    return _global_memory_store