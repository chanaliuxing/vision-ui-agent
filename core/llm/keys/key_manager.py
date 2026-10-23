"""
API密钥管理和轮换
按照upgrade.md Sprint D规范实现
"""
import logging
import json
import os
import hashlib
import secrets
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class KeyConfig:
    """API密钥配置"""
    key_id: str
    provider: str
    model: str
    encrypted_key: str
    created_at: str
    expires_at: Optional[str] = None
    usage_count: int = 0
    last_used: Optional[str] = None
    daily_limit: Optional[int] = None
    monthly_limit: Optional[int] = None
    is_active: bool = True
    tags: List[str] = None


class KeyManager:
    """API密钥管理器"""

    def __init__(self, vault_path: str = None, master_key: str = None):
        self.vault_path = Path(vault_path or "data/keys.vault")
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)

        # 初始化加密密钥
        if master_key:
            key_bytes = hashlib.sha256(master_key.encode()).digest()[:32]
            self.cipher = Fernet(Fernet.generate_key())
        else:
            # 从环境变量获取或生成
            env_key = os.environ.get("KEY_VAULT_MASTER")
            if env_key:
                key_bytes = hashlib.sha256(env_key.encode()).digest()[:32]
                self.cipher = Fernet(Fernet.generate_key())
            else:
                # 生成新密钥并保存到临时文件
                self.cipher = Fernet(Fernet.generate_key())
                logger.warning("Using generated master key - set KEY_VAULT_MASTER for production")

        self.keys: Dict[str, KeyConfig] = {}
        self.usage_stats: Dict[str, Dict] = {}
        self._load_vault()

    def add_key(self,
                provider: str,
                model: str,
                api_key: str,
                daily_limit: int = None,
                monthly_limit: int = None,
                expires_days: int = None,
                tags: List[str] = None) -> str:
        """添加API密钥"""

        key_id = self._generate_key_id(provider, model)
        encrypted_key = self._encrypt_key(api_key)

        expires_at = None
        if expires_days:
            expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()

        key_config = KeyConfig(
            key_id=key_id,
            provider=provider,
            model=model,
            encrypted_key=encrypted_key,
            created_at=datetime.now().isoformat(),
            expires_at=expires_at,
            daily_limit=daily_limit,
            monthly_limit=monthly_limit,
            tags=tags or []
        )

        self.keys[key_id] = key_config
        self.usage_stats[key_id] = {
            "daily_usage": {},
            "monthly_usage": {},
            "total_requests": 0,
            "total_tokens": 0,
            "last_reset": datetime.now().isoformat()
        }

        self._save_vault()
        logger.info(f"Added API key: {key_id} for {provider}:{model}")
        return key_id

    def get_key(self, provider: str, model: str, user_id: str = None) -> Optional[str]:
        """获取可用的API密钥"""

        # 按优先级查找密钥
        candidates = []
        for key_id, config in self.keys.items():
            if not config.is_active:
                continue

            if config.provider != provider or config.model != model:
                continue

            # 检查过期
            if config.expires_at:
                expires = datetime.fromisoformat(config.expires_at)
                if datetime.now() > expires:
                    continue

            # 检查使用限制
            if not self._check_usage_limits(key_id):
                continue

            # 计算优先级评分
            score = self._calculate_key_score(key_id)
            candidates.append((score, key_id, config))

        if not candidates:
            logger.warning(f"No available API keys for {provider}:{model}")
            return None

        # 选择最佳密钥
        candidates.sort(key=lambda x: x[0], reverse=True)
        selected_config = candidates[0][2]

        # 更新使用统计
        self._record_key_usage(selected_config.key_id)

        # 解密并返回
        decrypted_key = self._decrypt_key(selected_config.encrypted_key)
        logger.info(f"Selected API key: {selected_config.key_id}")
        return decrypted_key

    def rotate_key(self, key_id: str, new_api_key: str) -> bool:
        """轮换API密钥"""

        if key_id not in self.keys:
            logger.error(f"Key not found: {key_id}")
            return False

        config = self.keys[key_id]
        old_encrypted = config.encrypted_key

        try:
            # 加密新密钥
            config.encrypted_key = self._encrypt_key(new_api_key)

            # 重置使用统计
            config.usage_count = 0
            config.last_used = None

            self._save_vault()
            logger.info(f"Rotated API key: {key_id}")
            return True

        except Exception as e:
            # 回滚
            config.encrypted_key = old_encrypted
            logger.error(f"Failed to rotate key {key_id}: {e}")
            return False

    def deactivate_key(self, key_id: str) -> bool:
        """停用API密钥"""

        if key_id not in self.keys:
            return False

        self.keys[key_id].is_active = False
        self._save_vault()
        logger.info(f"Deactivated API key: {key_id}")
        return True

    def get_usage_stats(self, key_id: str = None) -> Dict:
        """获取使用统计"""

        if key_id:
            if key_id in self.usage_stats:
                stats = self.usage_stats[key_id].copy()
                config = self.keys.get(key_id)
                if config:
                    stats["key_info"] = {
                        "provider": config.provider,
                        "model": config.model,
                        "created_at": config.created_at,
                        "is_active": config.is_active
                    }
                return stats
            return {}

        # 返回所有密钥的统计
        all_stats = {}
        for kid, stats in self.usage_stats.items():
            config = self.keys.get(kid)
            if config:
                all_stats[kid] = {
                    "provider": config.provider,
                    "model": config.model,
                    "usage": stats,
                    "is_active": config.is_active
                }

        return all_stats

    def list_keys(self, provider: str = None, active_only: bool = True) -> List[Dict]:
        """列出API密钥"""

        keys_list = []
        for key_id, config in self.keys.items():
            if active_only and not config.is_active:
                continue

            if provider and config.provider != provider:
                continue

            key_info = {
                "key_id": key_id,
                "provider": config.provider,
                "model": config.model,
                "created_at": config.created_at,
                "expires_at": config.expires_at,
                "usage_count": config.usage_count,
                "last_used": config.last_used,
                "is_active": config.is_active,
                "tags": config.tags
            }

            # 添加使用统计
            if key_id in self.usage_stats:
                stats = self.usage_stats[key_id]
                key_info["total_requests"] = stats.get("total_requests", 0)
                key_info["total_tokens"] = stats.get("total_tokens", 0)

            keys_list.append(key_info)

        return keys_list

    def _generate_key_id(self, provider: str, model: str) -> str:
        """生成密钥ID"""
        timestamp = int(datetime.now().timestamp())
        random_suffix = secrets.token_hex(4)
        return f"{provider}_{model}_{timestamp}_{random_suffix}"

    def _encrypt_key(self, api_key: str) -> str:
        """加密API密钥"""
        return self.cipher.encrypt(api_key.encode()).decode()

    def _decrypt_key(self, encrypted_key: str) -> str:
        """解密API密钥"""
        return self.cipher.decrypt(encrypted_key.encode()).decode()

    def _check_usage_limits(self, key_id: str) -> bool:
        """检查使用限制"""
        config = self.keys.get(key_id)
        if not config:
            return False

        stats = self.usage_stats.get(key_id, {})
        today = datetime.now().date().isoformat()
        month = datetime.now().strftime("%Y-%m")

        # 检查日限制
        if config.daily_limit:
            daily_usage = stats.get("daily_usage", {}).get(today, 0)
            if daily_usage >= config.daily_limit:
                return False

        # 检查月限制
        if config.monthly_limit:
            monthly_usage = stats.get("monthly_usage", {}).get(month, 0)
            if monthly_usage >= config.monthly_limit:
                return False

        return True

    def _calculate_key_score(self, key_id: str) -> float:
        """计算密钥优先级评分"""
        config = self.keys[key_id]
        stats = self.usage_stats.get(key_id, {})

        score = 100.0

        # 使用量越少优先级越高
        total_requests = stats.get("total_requests", 0)
        score -= total_requests * 0.01

        # 最近使用时间权重
        if config.last_used:
            last_used = datetime.fromisoformat(config.last_used)
            hours_since_use = (datetime.now() - last_used).total_seconds() / 3600
            score += min(hours_since_use * 0.1, 10)  # 最多加10分

        # 剩余额度权重
        if config.daily_limit:
            today = datetime.now().date().isoformat()
            daily_used = stats.get("daily_usage", {}).get(today, 0)
            remaining_ratio = (config.daily_limit - daily_used) / config.daily_limit
            score += remaining_ratio * 20

        return score

    def _record_key_usage(self, key_id: str):
        """记录密钥使用"""
        config = self.keys[key_id]
        config.usage_count += 1
        config.last_used = datetime.now().isoformat()

        # 更新统计
        if key_id not in self.usage_stats:
            self.usage_stats[key_id] = {
                "daily_usage": {},
                "monthly_usage": {},
                "total_requests": 0,
                "total_tokens": 0,
                "last_reset": datetime.now().isoformat()
            }

        stats = self.usage_stats[key_id]
        stats["total_requests"] += 1

        today = datetime.now().date().isoformat()
        month = datetime.now().strftime("%Y-%m")

        # 日统计
        if today not in stats["daily_usage"]:
            stats["daily_usage"][today] = 0
        stats["daily_usage"][today] += 1

        # 月统计
        if month not in stats["monthly_usage"]:
            stats["monthly_usage"][month] = 0
        stats["monthly_usage"][month] += 1

        self._save_vault()

    def _load_vault(self):
        """加载密钥库"""
        try:
            if self.vault_path.exists():
                with open(self.vault_path, 'r') as f:
                    data = json.load(f)

                # 加载密钥配置
                for key_data in data.get("keys", []):
                    config = KeyConfig(**key_data)
                    self.keys[config.key_id] = config

                # 加载使用统计
                self.usage_stats = data.get("usage_stats", {})

                logger.info(f"Loaded {len(self.keys)} API keys from vault")
        except Exception as e:
            logger.error(f"Failed to load key vault: {e}")

    def _save_vault(self):
        """保存密钥库"""
        try:
            data = {
                "keys": [asdict(config) for config in self.keys.values()],
                "usage_stats": self.usage_stats,
                "saved_at": datetime.now().isoformat()
            }

            with open(self.vault_path, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save key vault: {e}")


# 全局密钥管理器
key_manager = KeyManager()