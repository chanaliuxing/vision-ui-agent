"""
Web回放UI服务器 - 按照upgrade.md Sprint F要求
提供Web界面回放工作流执行过程，支持定位具体失败步骤
"""
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

try:
    from fastapi import FastAPI, WebSocket, HTTPException, Request
    from fastapi.responses import HTMLResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    print("Warning: FastAPI not available. Web UI will use simple HTTP server.")

from .run_events import RunEventRecorder, EventType

logger = logging.getLogger(__name__)


class ReplayUIServer:
    """Web回放UI服务器"""

    def __init__(self, event_recorder: RunEventRecorder, port: int = 8888):
        self.event_recorder = event_recorder
        self.port = port
        self.app = None
        self.templates = None

        if FASTAPI_AVAILABLE:
            self._setup_fastapi()
        else:
            self._setup_simple_server()

    def _setup_fastapi(self):
        """设置FastAPI应用"""
        self.app = FastAPI(title="Workflow Replay UI", version="1.0.0")

        # 路由设置
        self._setup_routes()

    def _setup_routes(self):
        """设置路由"""

        @self.app.get("/", response_class=HTMLResponse)
        async def home():
            """主页 - 显示运行历史"""
            runs = self._get_recent_runs()
            return HTMLResponse(self._render_index(runs))

        @self.app.get("/replay/{run_id}", response_class=HTMLResponse)
        async def replay_page(run_id: str):
            """回放页面"""
            events = self.event_recorder.get_run_events(run_id)
            if not events:
                raise HTTPException(status_code=404, detail="Run not found")

            timeline = self._build_timeline(events)
            return HTMLResponse(self._render_replay(run_id, timeline))

        @self.app.get("/api/runs")
        async def get_runs():
            """获取运行列表API"""
            return {"runs": self._get_recent_runs()}

        @self.app.get("/api/runs/{run_id}/events")
        async def get_run_events(run_id: str):
            """获取运行事件API"""
            events = self.event_recorder.get_run_events(run_id)
            if not events:
                raise HTTPException(status_code=404, detail="Run not found")

            return {
                "run_id": run_id,
                "events": [self._serialize_event(event) for event in events],
                "timeline": self._build_timeline(events)
            }

        @self.app.get("/api/runs/{run_id}/screenshots/{step_id}")
        async def get_screenshot(run_id: str, step_id: str):
            """获取截图"""
            # 实际中应该从存储中获取截图
            screenshot_path = Path(f"out/screens/{run_id}_{step_id}.png")
            if screenshot_path.exists():
                return FileResponse(screenshot_path)
            else:
                raise HTTPException(status_code=404, detail="Screenshot not found")

    def _setup_simple_server(self):
        """设置简单HTTP服务器（fallback）"""
        import http.server
        import socketserver

        class SimpleHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                self.replay_server = kwargs.pop('replay_server', None)
                super().__init__(*args, **kwargs)

            def do_GET(self):
                if self.path == "/":
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(self._get_simple_index().encode())
                else:
                    super().do_GET()

            def _get_simple_index(self):
                return """
                <!DOCTYPE html>
                <html>
                <head><title>Workflow Replay (Simple)</title></head>
                <body>
                    <h1>Workflow Replay UI</h1>
                    <p>FastAPI not available. This is a simplified interface.</p>
                    <p>Install FastAPI for full functionality: pip install fastapi uvicorn</p>
                </body>
                </html>
                """

        self.server = socketserver.TCPServer(("", self.port), SimpleHandler)

    def _get_recent_runs(self) -> List[Dict]:
        """获取最近的运行记录"""
        runs = []

        # 从事件记录器获取所有运行
        all_run_ids = set()

        # 添加活跃运行
        for run_id in self.event_recorder.active_runs.keys():
            all_run_ids.add(run_id)

        # 添加历史运行（从事件历史中提取）
        for events in self.event_recorder.run_events.values():
            for event in events:
                if hasattr(event, 'run_id'):
                    all_run_ids.add(event.run_id)

        for run_id in all_run_ids:
            events = self.event_recorder.get_run_events(run_id)
            status = "running" if run_id in self.event_recorder.active_runs else "completed"

            # 检查是否有错误
            error_events = [e for e in events if e.event_type == EventType.ERROR]
            if error_events:
                status = "failed"

            # 获取开始时间
            start_time = None
            if run_id in self.event_recorder.active_runs:
                start_time = self.event_recorder.active_runs[run_id]
            elif events:
                start_time = events[0].timestamp if hasattr(events[0], 'timestamp') else datetime.now()

            runs.append({
                "run_id": run_id,
                "start_time": start_time.isoformat() if isinstance(start_time, datetime) else str(start_time),
                "status": status,
                "event_count": len(events),
                "error_count": len(error_events)
            })

        # 按时间倒序排列
        runs.sort(key=lambda x: x["start_time"], reverse=True)
        return runs[:50]  # 最近50个

    def _build_timeline(self, events) -> List[Dict]:
        """构建时间线数据"""
        timeline = []

        for i, event in enumerate(events):
            timeline_item = {
                "id": i,
                "timestamp": event.timestamp.isoformat() if hasattr(event, 'timestamp') else "",
                "event_type": event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type),
                "title": self._get_event_title(event),
                "description": self._get_event_description(event),
                "status": self._get_event_status(event),
                "has_screenshot": self._has_screenshot(event),
                "data": event.data if hasattr(event, 'data') else {}
            }
            timeline.append(timeline_item)

        return timeline

    def _get_event_title(self, event) -> str:
        """获取事件标题"""
        if event.event_type == EventType.STEP_START:
            return f"Step: {event.data.get('action', 'Unknown')}"
        elif event.event_type == EventType.STEP_END:
            return f"Completed: {event.data.get('action', 'Unknown')}"
        elif event.event_type == EventType.ERROR:
            return "Error Occurred"
        elif event.event_type == EventType.LLM_REQUEST:
            return "LLM Request"
        elif event.event_type == EventType.LLM_RESPONSE:
            return "LLM Response"
        else:
            return event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)

    def _get_event_description(self, event) -> str:
        """获取事件描述"""
        if hasattr(event, 'data') and event.data:
            if event.event_type == EventType.ERROR:
                return event.data.get('error_message', 'Unknown error')
            elif event.event_type == EventType.STEP_START:
                args = event.data.get('args', {})
                return f"Args: {json.dumps(args)[:100]}..."
            elif event.event_type == EventType.LLM_REQUEST:
                return f"Provider: {event.data.get('provider', 'Unknown')}"

        return ""

    def _get_event_status(self, event) -> str:
        """获取事件状态"""
        if event.event_type == EventType.ERROR:
            return "error"
        elif event.event_type == EventType.STEP_END:
            return "success" if event.data.get('success', True) else "error"
        else:
            return "info"

    def _has_screenshot(self, event) -> bool:
        """检查是否有截图"""
        # 简化实现，实际中应检查文件系统
        return event.event_type in [EventType.STEP_START, EventType.STEP_END]

    def _serialize_event(self, event) -> Dict:
        """序列化事件"""
        return {
            "event_type": event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type),
            "timestamp": event.timestamp.isoformat() if hasattr(event, 'timestamp') else "",
            "data": event.data if hasattr(event, 'data') else {},
            "run_id": event.run_id if hasattr(event, 'run_id') else ""
        }

    def _render_index(self, runs: List[Dict]) -> str:
        """渲染主页"""
        runs_html = ""
        for run in runs:
            status_class = run["status"]
            runs_html += f"""
            <div class="run-item">
                <h3><a href="/replay/{run['run_id']}">{run['run_id']}</a></h3>
                <p>
                    <span class="status {status_class}">{run['status']}</span>
                    Started: {run['start_time']} |
                    Events: {run['event_count']} |
                    Errors: {run['error_count']}
                </p>
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Workflow Replay UI</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .run-item {{ border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; }}
                .status {{ padding: 3px 8px; border-radius: 3px; color: white; font-size: 12px; }}
                .status.completed {{ background-color: #28a745; }}
                .status.failed {{ background-color: #dc3545; }}
                .status.running {{ background-color: #007bff; }}
                a {{ text-decoration: none; color: #007bff; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <h1>🎬 Workflow Replay UI</h1>
            <p>按照upgrade.md Sprint F要求实现的Web回放界面</p>
            <h2>Recent Runs</h2>
            {runs_html}
        </body>
        </html>
        """

    def _render_replay(self, run_id: str, timeline: List[Dict]) -> str:
        """渲染回放页面"""
        timeline_html = ""
        for item in timeline:
            screenshot_link = ""
            if item["has_screenshot"]:
                screenshot_link = f'<p><a href="/api/runs/{run_id}/screenshots/{item["id"]}">📸 View Screenshot</a></p>'

            data_section = ""
            if item["data"]:
                data_json = json.dumps(item["data"], indent=2)
                data_section = f"""
                <details>
                    <summary>Event Data</summary>
                    <div class="event-data">
                        <pre>{data_json}</pre>
                    </div>
                </details>
                """

            timeline_html += f"""
            <div class="timeline-item {item['status']}">
                <div class="timestamp">{item['timestamp']}</div>
                <h4>{item['title']}</h4>
                <p>{item['description']}</p>
                {screenshot_link}
                {data_section}
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Replay: {run_id}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .timeline {{ border-left: 2px solid #ddd; margin-left: 20px; }}
                .timeline-item {{ margin: 20px 0; padding-left: 20px; position: relative; }}
                .timeline-item::before {{
                    content: ""; width: 10px; height: 10px; background: #007bff;
                    border-radius: 50%; position: absolute; left: -6px; top: 5px;
                }}
                .error::before {{ background: #dc3545; }}
                .success::before {{ background: #28a745; }}
                .timestamp {{ color: #666; font-size: 12px; }}
                .event-data {{ background: #f8f9fa; padding: 10px; margin-top: 10px; border-radius: 3px; }}
                a {{ color: #007bff; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                pre {{ overflow-x: auto; }}
            </style>
        </head>
        <body>
            <h1>🎬 Replay: {run_id}</h1>
            <a href="/">← Back to Runs</a>

            <div class="timeline">
                {timeline_html}
            </div>
        </body>
        </html>
        """

    async def start(self):
        """启动服务器"""
        if FASTAPI_AVAILABLE:
            logger.info(f"Starting Web Replay UI on http://localhost:{self.port}")
            config = uvicorn.Config(self.app, host="0.0.0.0", port=self.port)
            server = uvicorn.Server(config)
            await server.serve()
        else:
            logger.info(f"Starting simple replay server on http://localhost:{self.port}")
            self.server.serve_forever()

    def start_sync(self):
        """同步启动服务器"""
        if FASTAPI_AVAILABLE:
            uvicorn.run(self.app, host="0.0.0.0", port=self.port)
        else:
            self.server.serve_forever()


def create_replay_ui(event_recorder: RunEventRecorder, port: int = 8888) -> ReplayUIServer:
    """创建回放UI服务器"""
    return ReplayUIServer(event_recorder, port)