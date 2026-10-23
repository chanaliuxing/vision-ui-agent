from dataclasses import dataclass, field
from typing import Any, Dict

@dataclass
class Services:
    dom: Any     # 提供 open/exists/extract/go_back/click 等
    os: Any      # 提供 move_to/click/scroll
    vision: Any  # 预留
    mq: Any      # ★ 新增：消息总线（阶段2本地，阶段3换成 Rabbit/SQS）
    logger: Any

@dataclass
class Ctx:
    vars: Dict[str, Any] = field(default_factory=dict)
    last_result: Any = None
    services: Services = None
    run_id: str = "dev"
    artifacts_dir: str = "artifacts"