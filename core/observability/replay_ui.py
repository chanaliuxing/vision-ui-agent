"""
Web回放UI服务器
按照upgrade.md Sprint F规范实现
"""
import logging
import json
import base64
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS

from .run_events import event_recorder, EventType, SensitivityLevel
from .sla_monitor import sla_monitor

logger = logging.getLogger(__name__)


class ReplayUIServer:
    """回放UI服务器"""

    def __init__(self, port: int = 8080):
        self.app = Flask(__name__,
                        template_folder='templates',
                        static_folder='static')
        CORS(self.app)
        self.port = port

        # 注册路由
        self._setup_routes()

    def _setup_routes(self):
        """设置路由"""

        @self.app.route('/')
        def index():
            """首页 - 运行列表"""
            return render_template('replay_index.html')

        @self.app.route('/api/runs')
        def get_runs():
            """获取运行列表"""
            try:
                runs = self._get_available_runs()
                return jsonify({
                    "success": True,
                    "data": runs
                })
            except Exception as e:
                logger.error(f"Failed to get runs: {e}")
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.app.route('/api/runs/<run_id>')
        def get_run_details(run_id):
            """获取运行详情"""
            try:
                events = event_recorder.get_run_events(run_id, sanitize=True)
                timeline = event_recorder.get_event_timeline(run_id)

                return jsonify({
                    "success": True,
                    "data": {
                        "run_id": run_id,
                        "events": [self._event_to_dict(event) for event in events],
                        "timeline": timeline,
                        "summary": self._generate_run_summary(events)
                    }
                })
            except Exception as e:
                logger.error(f"Failed to get run details: {e}")
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.app.route('/api/runs/<run_id>/replay')
        def replay_run(run_id):
            """回放运行"""
            return render_template('replay_player.html', run_id=run_id)

        @self.app.route('/api/runs/<run_id>/screenshots/<event_id>')
        def get_screenshot(run_id, event_id):
            """获取截图"""
            try:
                events = event_recorder.get_run_events(run_id, sanitize=False)
                screenshot_event = next((e for e in events if e.event_id == event_id), None)

                if not screenshot_event or screenshot_event.event_type != EventType.SCREENSHOT:
                    return jsonify({"error": "Screenshot not found"}), 404

                screenshot_path = screenshot_event.data.get('screenshot_path')
                if not screenshot_path or not Path(screenshot_path).exists():
                    return jsonify({"error": "Screenshot file not found"}), 404

                return send_file(screenshot_path, mimetype='image/png')

            except Exception as e:
                logger.error(f"Failed to get screenshot: {e}")
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/runs/<run_id>/variables')
        def get_variables(run_id):
            """获取变量历史"""
            try:
                events = event_recorder.get_run_events(run_id, sanitize=True)
                variable_events = [e for e in events if e.event_type == EventType.VARIABLE_SET]

                variables = {}
                variable_history = []

                for event in variable_events:
                    var_name = event.data.get('variable_name')
                    var_value = event.data.get('value')

                    variables[var_name] = var_value
                    variable_history.append({
                        "timestamp": event.timestamp,
                        "step_id": event.step_id,
                        "variable_name": var_name,
                        "value": var_value,
                        "value_type": event.data.get('value_type')
                    })

                return jsonify({
                    "success": True,
                    "data": {
                        "current_variables": variables,
                        "variable_history": variable_history
                    }
                })

            except Exception as e:
                logger.error(f"Failed to get variables: {e}")
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.app.route('/api/dashboard/sla')
        def sla_dashboard():
            """SLA仪表盘"""
            try:
                dashboard_data = sla_monitor.get_sla_dashboard_data()
                return jsonify({
                    "success": True,
                    "data": dashboard_data
                })
            except Exception as e:
                logger.error(f"Failed to get SLA dashboard: {e}")
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.app.route('/api/alerts')
        def get_alerts():
            """获取告警列表"""
            try:
                alerts = sla_monitor.get_active_alerts()
                return jsonify({
                    "success": True,
                    "data": [self._alert_to_dict(alert) for alert in alerts]
                })
            except Exception as e:
                logger.error(f"Failed to get alerts: {e}")
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.app.route('/api/search')
        def search_events():
            """搜索事件"""
            try:
                query = request.args.get('q', '')
                run_id = request.args.get('run_id')
                event_type = request.args.get('event_type')

                # 实现搜索逻辑
                results = self._search_events(query, run_id, event_type)

                return jsonify({
                    "success": True,
                    "data": results
                })
            except Exception as e:
                logger.error(f"Search failed: {e}")
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

    def _get_available_runs(self) -> List[Dict]:
        """获取可用的运行列表"""
        runs = []
        storage_path = event_recorder.storage_path

        for run_file in storage_path.glob("run_*.json"):
            try:
                run_id = run_file.stem.replace("run_", "")
                with open(run_file, 'r') as f:
                    events_data = json.load(f)

                if not events_data:
                    continue

                # 找到开始和结束事件
                start_event = next((e for e in events_data if e['event_type'] == 'workflow_start'), None)
                end_event = next((e for e in events_data if e['event_type'] == 'workflow_end'), None)

                if not start_event:
                    continue

                runs.append({
                    "run_id": run_id,
                    "workflow_id": start_event.get('workflow_id', 'unknown'),
                    "start_time": start_event.get('timestamp'),
                    "end_time": end_event.get('timestamp') if end_event else None,
                    "success": end_event.get('data', {}).get('success', None) if end_event else None,
                    "event_count": len(events_data),
                    "duration_seconds": self._calculate_duration(start_event, end_event)
                })

            except Exception as e:
                logger.error(f"Failed to parse run file {run_file}: {e}")

        # 按时间倒序排列
        runs.sort(key=lambda x: x['start_time'], reverse=True)
        return runs

    def _calculate_duration(self, start_event: Dict, end_event: Dict) -> Optional[float]:
        """计算运行持续时间"""
        if not start_event or not end_event:
            return None

        try:
            start_time = datetime.fromisoformat(start_event['timestamp'])
            end_time = datetime.fromisoformat(end_event['timestamp'])
            return (end_time - start_time).total_seconds()
        except:
            return None

    def _event_to_dict(self, event) -> Dict:
        """转换事件为字典"""
        return {
            "event_id": event.event_id,
            "timestamp": event.timestamp,
            "event_type": event.event_type.value,
            "run_id": event.run_id,
            "workflow_id": event.workflow_id,
            "step_id": event.step_id,
            "action_id": event.action_id,
            "data": event.data,
            "metadata": event.metadata,
            "duration_ms": event.duration_ms,
            "error_type": event.error_type,
            "error_message": event.error_message,
            "sensitivity": event.sensitivity.value if event.sensitivity else None,
            "is_sanitized": event.is_sanitized
        }

    def _alert_to_dict(self, alert) -> Dict:
        """转换告警为字典"""
        return {
            "alert_id": alert.alert_id,
            "timestamp": alert.timestamp.isoformat(),
            "level": alert.level.value,
            "status": alert.status.value,
            "title": alert.title,
            "message": alert.message,
            "metric_type": alert.metric_type.value,
            "current_value": alert.current_value,
            "target_value": alert.target_value,
            "workflow_id": alert.workflow_id,
            "tags": alert.tags,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "resolved_by": alert.resolved_by
        }

    def _generate_run_summary(self, events) -> Dict:
        """生成运行摘要"""
        summary = {
            "total_events": len(events),
            "event_types": {},
            "steps_executed": set(),
            "actions_executed": set(),
            "errors": [],
            "screenshots_taken": 0,
            "llm_requests": 0,
            "variables_set": 0
        }

        for event in events:
            # 事件类型统计
            event_type = event.event_type.value
            summary["event_types"][event_type] = summary["event_types"].get(event_type, 0) + 1

            # 步骤和动作统计
            if event.step_id:
                summary["steps_executed"].add(event.step_id)
            if event.action_id:
                summary["actions_executed"].add(event.action_id)

            # 特定事件统计
            if event.event_type == EventType.ERROR:
                summary["errors"].append({
                    "timestamp": event.timestamp,
                    "step_id": event.step_id,
                    "error_type": event.error_type,
                    "error_message": event.error_message
                })
            elif event.event_type == EventType.SCREENSHOT:
                summary["screenshots_taken"] += 1
            elif event.event_type == EventType.LLM_REQUEST:
                summary["llm_requests"] += 1
            elif event.event_type == EventType.VARIABLE_SET:
                summary["variables_set"] += 1

        # 转换集合为列表
        summary["steps_executed"] = list(summary["steps_executed"])
        summary["actions_executed"] = list(summary["actions_executed"])

        return summary

    def _search_events(self, query: str, run_id: str = None, event_type: str = None) -> List[Dict]:
        """搜索事件"""
        results = []

        # 获取所有事件
        if run_id:
            events = event_recorder.get_run_events(run_id, sanitize=True)
        else:
            events = event_recorder.events

        for event in events:
            # 类型过滤
            if event_type and event.event_type.value != event_type:
                continue

            # 文本搜索
            if query:
                searchable_text = json.dumps({
                    "event_type": event.event_type.value,
                    "step_id": event.step_id,
                    "action_id": event.action_id,
                    "data": event.data,
                    "error_message": event.error_message
                }, default=str).lower()

                if query.lower() not in searchable_text:
                    continue

            results.append(self._event_to_dict(event))

        # 限制结果数量
        return results[:100]

    def run(self, debug: bool = False):
        """运行服务器"""
        logger.info(f"Starting replay UI server on port {self.port}")
        self.app.run(host='0.0.0.0', port=self.port, debug=debug)


# 创建HTML模板
def create_templates():
    """创建HTML模板"""
    template_dir = Path("templates")
    template_dir.mkdir(exist_ok=True)

    # 主页模板
    index_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>工作流回放系统</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; }
        .run-card {
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
            background: #f9f9f9;
        }
        .run-card:hover { background: #f0f0f0; cursor: pointer; }
        .run-status {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }
        .status-success { background: #d4edda; color: #155724; }
        .status-failed { background: #f8d7da; color: #721c24; }
        .status-unknown { background: #e2e3e5; color: #495057; }
        .run-meta { color: #666; font-size: 14px; margin-top: 5px; }
        .loading { text-align: center; padding: 20px; }
        .error { color: red; text-align: center; padding: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔄 工作流回放系统</h1>
            <p>查看和回放工作流执行历史</p>
        </div>

        <div id="runs-container">
            <div class="loading">正在加载运行记录...</div>
        </div>
    </div>

    <script>
        async function loadRuns() {
            try {
                const response = await fetch('/api/runs');
                const result = await response.json();

                if (result.success) {
                    displayRuns(result.data);
                } else {
                    showError('加载失败: ' + result.error);
                }
            } catch (error) {
                showError('网络错误: ' + error.message);
            }
        }

        function displayRuns(runs) {
            const container = document.getElementById('runs-container');

            if (runs.length === 0) {
                container.innerHTML = '<div class="error">暂无运行记录</div>';
                return;
            }

            let html = '';
            runs.forEach(run => {
                const statusClass = run.success === true ? 'status-success' :
                                   run.success === false ? 'status-failed' : 'status-unknown';
                const statusText = run.success === true ? '成功' :
                                  run.success === false ? '失败' : '未知';

                html += `
                    <div class="run-card" onclick="viewRun('${run.run_id}')">
                        <div>
                            <strong>${run.workflow_id}</strong>
                            <span class="run-status ${statusClass}">${statusText}</span>
                        </div>
                        <div class="run-meta">
                            运行ID: ${run.run_id}<br>
                            开始时间: ${new Date(run.start_time).toLocaleString()}<br>
                            事件数: ${run.event_count} |
                            持续时间: ${run.duration_seconds ? Math.round(run.duration_seconds) + 's' : '未知'}
                        </div>
                    </div>
                `;
            });

            container.innerHTML = html;
        }

        function showError(message) {
            const container = document.getElementById('runs-container');
            container.innerHTML = `<div class="error">${message}</div>`;
        }

        function viewRun(runId) {
            window.location.href = `/api/runs/${runId}/replay`;
        }

        // 页面加载时获取运行列表
        window.onload = loadRuns;
    </script>
</body>
</html>"""

    with open(template_dir / "replay_index.html", "w", encoding="utf-8") as f:
        f.write(index_html)

    # 回放器模板
    player_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>工作流回放 - {{ run_id }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 20px; }
        .player { display: flex; gap: 20px; }
        .timeline-panel { flex: 1; max-height: 80vh; overflow-y: auto; }
        .details-panel { flex: 1; }
        .event-item {
            padding: 10px;
            border: 1px solid #ddd;
            margin-bottom: 5px;
            border-radius: 4px;
            cursor: pointer;
        }
        .event-item:hover { background: #f0f0f0; }
        .event-item.active { background: #e3f2fd; border-color: #2196f3; }
        .event-type {
            font-weight: bold;
            color: #1976d2;
            font-size: 14px;
        }
        .event-time {
            color: #666;
            font-size: 12px;
            float: right;
        }
        .event-summary {
            color: #333;
            margin-top: 5px;
            font-size: 14px;
        }
        .details-content {
            background: #f9f9f9;
            padding: 15px;
            border-radius: 8px;
            max-height: 70vh;
            overflow-y: auto;
        }
        .screenshot {
            max-width: 100%;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .json-data {
            background: #2d3748;
            color: #fff;
            padding: 10px;
            border-radius: 4px;
            overflow-x: auto;
            font-family: monospace;
            font-size: 12px;
        }
        .back-btn {
            background: #2196f3;
            color: white;
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
        }
        .back-btn:hover { background: #1976d2; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <a href="/" class="back-btn">← 返回列表</a>
            <h1>🎬 工作流回放</h1>
            <p>运行ID: {{ run_id }}</p>
        </div>

        <div class="player">
            <div class="timeline-panel">
                <h3>事件时间线</h3>
                <div id="timeline-container">
                    <div style="text-align: center; padding: 20px;">正在加载事件...</div>
                </div>
            </div>

            <div class="details-panel">
                <h3>事件详情</h3>
                <div class="details-content" id="details-container">
                    <p>选择左侧事件查看详情</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        const runId = '{{ run_id }}';
        let currentEvents = [];
        let selectedEventIndex = -1;

        async function loadRunData() {
            try {
                const response = await fetch(`/api/runs/${runId}`);
                const result = await response.json();

                if (result.success) {
                    currentEvents = result.data.timeline;
                    displayTimeline(currentEvents);
                } else {
                    showError('加载失败: ' + result.error);
                }
            } catch (error) {
                showError('网络错误: ' + error.message);
            }
        }

        function displayTimeline(events) {
            const container = document.getElementById('timeline-container');

            let html = '';
            events.forEach((event, index) => {
                const time = new Date(event.timestamp).toLocaleTimeString();
                html += `
                    <div class="event-item" onclick="selectEvent(${index})" id="event-${index}">
                        <div class="event-time">${time}</div>
                        <div class="event-type">${event.event_type}</div>
                        <div class="event-summary">${event.summary}</div>
                    </div>
                `;
            });

            container.innerHTML = html;
        }

        function selectEvent(index) {
            // 清除之前选中的样式
            if (selectedEventIndex >= 0) {
                document.getElementById(`event-${selectedEventIndex}`)?.classList.remove('active');
            }

            // 设置新选中的样式
            selectedEventIndex = index;
            document.getElementById(`event-${index}`).classList.add('active');

            // 显示事件详情
            displayEventDetails(currentEvents[index]);
        }

        function displayEventDetails(event) {
            const container = document.getElementById('details-container');

            let html = `
                <h4>${event.event_type} - ${event.summary}</h4>
                <p><strong>时间:</strong> ${new Date(event.timestamp).toLocaleString()}</p>
            `;

            if (event.step_id) {
                html += `<p><strong>步骤ID:</strong> ${event.step_id}</p>`;
            }

            if (event.action_id) {
                html += `<p><strong>动作ID:</strong> ${event.action_id}</p>`;
            }

            if (event.duration_ms) {
                html += `<p><strong>耗时:</strong> ${event.duration_ms.toFixed(0)}ms</p>`;
            }

            // 处理截图
            if (event.event_type === 'screenshot' && event.data.screenshot_path) {
                // 这里需要从对应的事件ID获取截图
                // html += `<img src="/api/runs/${runId}/screenshots/${event.event_id}" class="screenshot" alt="截图">`;
                html += `<p><strong>截图:</strong> ${event.data.screenshot_path}</p>`;
            }

            // 显示事件数据
            if (event.data && Object.keys(event.data).length > 0) {
                html += `<h5>事件数据:</h5>`;
                html += `<div class="json-data">${JSON.stringify(event.data, null, 2)}</div>`;
            }

            container.innerHTML = html;
        }

        function showError(message) {
            document.getElementById('timeline-container').innerHTML = `<div style="color: red; text-align: center;">${message}</div>`;
        }

        // 页面加载时获取数据
        window.onload = loadRunData;
    </script>
</body>
</html>"""

    with open(template_dir / "replay_player.html", "w", encoding="utf-8") as f:
        f.write(player_html)

    logger.info("Created HTML templates")


if __name__ == "__main__":
    # 创建模板
    create_templates()

    # 启动服务器
    server = ReplayUIServer(port=8080)
    server.run(debug=True)