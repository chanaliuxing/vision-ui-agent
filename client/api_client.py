# client/api_client.py
import time, json, queue, threading, requests
from pathlib import Path
from typing import Dict, Any

class APIClient:
    def __init__(self, base_url: str, token: str = None, offline_mode: bool = False):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.offline_mode = offline_mode
        self.q = queue.Queue(maxsize=1024)
        self.offline_wal = Path("artifacts/offline_wal.jsonl")
        self.offline_wal.parent.mkdir(parents=True, exist_ok=True)

        # 启动后台线程处理队列
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.t.start()

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _loop(self):
        """后台线程：处理API调用队列"""
        while True:
            try:
                path, payload = self.q.get(timeout=1.0)
            except queue.Empty:
                continue

            if self.offline_mode:
                # 离线模式：写入WAL
                self._write_to_wal(path, payload)
            else:
                success = self._try_send(path, payload)
                if not success:
                    # 网络失败，写入WAL待重试
                    self._write_to_wal(path, payload)

    def _try_send(self, path: str, payload: Dict[str, Any]) -> bool:
        """尝试发送API请求"""
        try:
            url = f"{self.base_url}{path}"
            response = requests.post(
                url,
                headers=self._headers(),
                data=json.dumps(payload, ensure_ascii=False),
                timeout=5
            )
            return response.status_code < 400
        except Exception:
            return False

    def _write_to_wal(self, path: str, payload: Dict[str, Any]):
        """写入离线WAL日志"""
        record = {
            "ts": int(time.time()),
            "path": path,
            "payload": payload
        }
        with open(self.offline_wal, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def post_async(self, path: str, payload: Dict[str, Any]):
        """异步发送POST请求"""
        try:
            self.q.put((path, payload), block=False)
        except queue.Full:
            # 队列满时直接写WAL
            self._write_to_wal(path, payload)

    def sync_offline_wal(self) -> int:
        """同步离线WAL，返回处理的记录数"""
        if not self.offline_wal.exists():
            return 0

        processed = 0
        failed_records = []

        with open(self.offline_wal, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    success = self._try_send(record["path"], record["payload"])
                    if success:
                        processed += 1
                    else:
                        failed_records.append(line)
                except Exception:
                    failed_records.append(line)

        # 重写WAL，保留失败的记录
        with open(self.offline_wal, "w", encoding="utf-8") as f:
            for record in failed_records:
                f.write(record)

        return processed

    def _load_token(self):
        """从本地加载token"""
        p = Path.home() / ".autoagent" / "auth.json"
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return data.get("access_token")
            except Exception:
                pass
        return None

    def set_token(self, token: str):
        """设置认证token"""
        self.token = token

    def post(self, path: str, payload: Dict[str, Any]):
        """同步POST请求"""
        url = f"{self.base_url}{path}"
        response = requests.post(
            url,
            headers=self._headers(),
            data=json.dumps(payload, ensure_ascii=False),
            timeout=8
        )
        response.raise_for_status()
        return response.json()

    # === 设备注册与心跳 ===
    def register_device(self, machine_code: str, name: str, capabilities: Dict[str, Any]):
        """注册设备"""
        return self.post("/devices/register", {
            "machine_code": machine_code,
            "name": name,
            "capabilities": capabilities
        })

    def heartbeat(self, device_id: str):
        """发送心跳（异步）"""
        self.post_async("/devices/heartbeat", {"device_id": device_id})

    def list_devices(self):
        """获取设备列表"""
        url = f"{self.base_url}/devices/list"
        response = requests.get(
            url,
            headers=self._headers(),
            timeout=8
        )
        response.raise_for_status()
        return response.json()

    # === v1 pick helpers ===
    def pick_v1(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Call /v1/pick and return raw JSON response."""
        return self.post("/v1/pick", payload)

    @staticmethod
    def extract_click_from_pick_response(resp: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize /v1/pick result.
        Returns:
          {"clickable": bool, "point": [x,y]|None, "reason": str, "confidence": float|None}
        """
        data = resp.get("data") if isinstance(resp, dict) else None
        decision = (data or {}).get("decision") if isinstance(data, dict) else None
        if not isinstance(decision, dict):
            return {"clickable": False, "point": None, "reason": "missing_decision", "confidence": None}

        action = decision.get("action")
        point = decision.get("point_in_capture")
        conf = decision.get("confidence")
        reason = decision.get("reason") or ""

        if action != "click":
            return {"clickable": False, "point": None, "reason": reason or f"action={action}", "confidence": conf}
        if not isinstance(point, list) or len(point) != 2:
            return {"clickable": False, "point": None, "reason": "invalid_point", "confidence": conf}
        if int(point[0]) == 0 and int(point[1]) == 0:
            return {"clickable": False, "point": None, "reason": reason or "zero_point", "confidence": conf}
        return {"clickable": True, "point": [int(point[0]), int(point[1])], "reason": reason, "confidence": conf}
