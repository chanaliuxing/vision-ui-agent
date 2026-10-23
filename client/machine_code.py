# client/machine_code.py
import uuid, json
from pathlib import Path

def get_machine_code():
    """获取或生成机器识别码"""
    p = Path.home() / ".autoagent" / "device.json"
    p.parent.mkdir(parents=True, exist_ok=True)

    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data["machine_code"]
        except Exception:
            # 文件损坏，重新生成
            pass

    mc = str(uuid.uuid4())
    p.write_text(
        json.dumps({"machine_code": mc}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return mc