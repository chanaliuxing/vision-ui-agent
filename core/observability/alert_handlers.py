"""
告警处理器 - 多种告警通知方式
按照upgrade.md Sprint F规范实现
"""
import logging
import json
import smtplib
import requests
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

from .sla_monitor import Alert, AlertLevel

logger = logging.getLogger(__name__)


@dataclass
class AlertConfig:
    """告警配置"""
    enabled: bool = True
    min_alert_level: AlertLevel = AlertLevel.WARNING
    cooldown_minutes: int = 5  # 同类告警冷却时间
    max_alerts_per_hour: int = 20


@dataclass
class EmailConfig:
    """邮件配置"""
    smtp_server: str
    username: str
    password: str
    from_email: str
    to_emails: List[str]
    smtp_port: int = 587
    use_tls: bool = True


@dataclass
class WebhookConfig:
    """Webhook配置"""
    url: str
    method: str = "POST"
    headers: Optional[Dict[str, str]] = None
    timeout: int = 10

    def __post_init__(self):
        if self.headers is None:
            self.headers = {}


@dataclass
class SlackConfig:
    """Slack配置"""
    webhook_url: str
    channel: str = "#alerts"
    username: str = "SLA Monitor"
    icon_emoji: str = ":warning:"


class EmailAlertHandler:
    """邮件告警处理器"""

    def __init__(self, config: EmailConfig):
        self.config = config

    def send_alert(self, alert: Alert) -> bool:
        """发送告警邮件"""
        try:
            # 创建邮件内容
            msg = MIMEMultipart()
            msg['From'] = self.config.from_email
            msg['To'] = ', '.join(self.config.to_emails)
            msg['Subject'] = f"[{alert.level.value.upper()}] {alert.title}"

            # 邮件正文
            body = self._generate_email_body(alert)
            msg.attach(MIMEText(body, 'html'))

            # 发送邮件
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                if self.config.use_tls:
                    server.starttls()

                if self.config.username and self.config.password:
                    server.login(self.config.username, self.config.password)

                server.send_message(msg)

            logger.info(f"Alert email sent: {alert.alert_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send alert email: {e}")
            return False

    def _generate_email_body(self, alert: Alert) -> str:
        """生成邮件正文"""
        level_colors = {
            AlertLevel.INFO: "#2196F3",
            AlertLevel.WARNING: "#FF9800",
            AlertLevel.CRITICAL: "#F44336",
            AlertLevel.EMERGENCY: "#9C27B0"
        }

        color = level_colors.get(alert.level, "#666666")

        return f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto;">
                <div style="background: {color}; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
                    <h1 style="margin: 0; font-size: 24px;">
                        🚨 {alert.title}
                    </h1>
                </div>

                <div style="background: #f9f9f9; padding: 20px; border-radius: 0 0 8px 8px;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">告警级别:</td>
                            <td style="padding: 8px; border-bottom: 1px solid #ddd;">{alert.level.value.upper()}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">时间:</td>
                            <td style="padding: 8px; border-bottom: 1px solid #ddd;">{alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">指标类型:</td>
                            <td style="padding: 8px; border-bottom: 1px solid #ddd;">{alert.metric_type.value}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">当前值:</td>
                            <td style="padding: 8px; border-bottom: 1px solid #ddd;">{alert.current_value:.4f}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">目标值:</td>
                            <td style="padding: 8px; border-bottom: 1px solid #ddd;">{alert.target_value:.4f}</td>
                        </tr>
                        {f'<tr><td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">工作流:</td><td style="padding: 8px; border-bottom: 1px solid #ddd;">{alert.workflow_id}</td></tr>' if alert.workflow_id else ''}
                    </table>

                    <div style="margin-top: 20px; padding: 15px; background: white; border-radius: 4px; border-left: 4px solid {color};">
                        <h3 style="margin-top: 0;">详细信息:</h3>
                        <p>{alert.message}</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """


class SlackAlertHandler:
    """Slack告警处理器"""

    def __init__(self, config: SlackConfig):
        self.config = config

    def send_alert(self, alert: Alert) -> bool:
        """发送Slack告警"""
        try:
            # 选择颜色和表情
            level_info = {
                AlertLevel.INFO: {"color": "#2196F3", "emoji": ":information_source:"},
                AlertLevel.WARNING: {"color": "#FF9800", "emoji": ":warning:"},
                AlertLevel.CRITICAL: {"color": "#F44336", "emoji": ":rotating_light:"},
                AlertLevel.EMERGENCY: {"color": "#9C27B0", "emoji": ":fire:"}
            }

            info = level_info.get(alert.level, {"color": "#666666", "emoji": ":exclamation:"})

            # 构建Slack消息
            payload = {
                "channel": self.config.channel,
                "username": self.config.username,
                "icon_emoji": self.config.icon_emoji,
                "attachments": [
                    {
                        "color": info["color"],
                        "title": f"{info['emoji']} {alert.title}",
                        "fields": [
                            {
                                "title": "级别",
                                "value": alert.level.value.upper(),
                                "short": True
                            },
                            {
                                "title": "指标类型",
                                "value": alert.metric_type.value,
                                "short": True
                            },
                            {
                                "title": "当前值",
                                "value": f"{alert.current_value:.4f}",
                                "short": True
                            },
                            {
                                "title": "目标值",
                                "value": f"{alert.target_value:.4f}",
                                "short": True
                            },
                            {
                                "title": "详细信息",
                                "value": alert.message,
                                "short": False
                            }
                        ],
                        "timestamp": int(alert.timestamp.timestamp())
                    }
                ]
            }

            if alert.workflow_id:
                payload["attachments"][0]["fields"].insert(-1, {
                    "title": "工作流",
                    "value": alert.workflow_id,
                    "short": True
                })

            # 发送到Slack
            response = requests.post(
                self.config.webhook_url,
                json=payload,
                timeout=10
            )
            response.raise_for_status()

            logger.info(f"Alert sent to Slack: {alert.alert_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False


class WebhookAlertHandler:
    """Webhook告警处理器"""

    def __init__(self, config: WebhookConfig):
        self.config = config

    def send_alert(self, alert: Alert) -> bool:
        """发送Webhook告警"""
        try:
            # 构建请求数据
            payload = {
                "alert_id": alert.alert_id,
                "timestamp": alert.timestamp.isoformat(),
                "level": alert.level.value,
                "title": alert.title,
                "message": alert.message,
                "metric_type": alert.metric_type.value,
                "current_value": alert.current_value,
                "target_value": alert.target_value,
                "workflow_id": alert.workflow_id,
                "tags": alert.tags or {}
            }

            headers = self.config.headers or {"Content-Type": "application/json"}

            # 发送HTTP请求
            response = requests.request(
                method=self.config.method,
                url=self.config.url,
                json=payload,
                headers=headers,
                timeout=self.config.timeout
            )
            response.raise_for_status()

            logger.info(f"Alert sent via webhook: {alert.alert_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")
            return False


class ConsoleAlertHandler:
    """控制台告警处理器"""

    def send_alert(self, alert: Alert) -> bool:
        """输出告警到控制台"""
        try:
            level_symbols = {
                AlertLevel.INFO: "ℹ️",
                AlertLevel.WARNING: "⚠️",
                AlertLevel.CRITICAL: "🚨",
                AlertLevel.EMERGENCY: "🔥"
            }

            symbol = level_symbols.get(alert.level, "❗")

            print(f"\n{symbol} ALERT [{alert.level.value.upper()}] {symbol}")
            print("=" * 50)
            print(f"Title: {alert.title}")
            print(f"Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Metric: {alert.metric_type.value}")
            print(f"Current: {alert.current_value:.4f}")
            print(f"Target: {alert.target_value:.4f}")
            if alert.workflow_id:
                print(f"Workflow: {alert.workflow_id}")
            print(f"Message: {alert.message}")
            print("=" * 50)

            return True

        except Exception as e:
            logger.error(f"Failed to print console alert: {e}")
            return False


class AlertManager:
    """告警管理器"""

    def __init__(self, config_path: str = "config/alert_config.json"):
        self.config_path = Path(config_path)
        self.config = AlertConfig()
        self.handlers: List[Callable[[Alert], bool]] = []
        self.alert_history: Dict[str, datetime] = {}  # alert_key -> last_sent_time

        # 加载配置
        self._load_config()

        # 默认添加控制台处理器
        console_handler = ConsoleAlertHandler()
        self.add_handler(console_handler.send_alert)

    def _load_config(self):
        """加载配置"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config_data = json.load(f)

                self.config.enabled = config_data.get('enabled', True)
                self.config.min_alert_level = AlertLevel(config_data.get('min_alert_level', 'warning'))
                self.config.cooldown_minutes = config_data.get('cooldown_minutes', 5)
                self.config.max_alerts_per_hour = config_data.get('max_alerts_per_hour', 20)

                # 加载各种处理器配置
                self._setup_handlers(config_data)

                logger.info("Alert configuration loaded")

        except Exception as e:
            logger.error(f"Failed to load alert config: {e}")

    def _setup_handlers(self, config_data: Dict):
        """设置处理器"""
        # Email处理器
        email_config = config_data.get('email')
        if email_config and email_config.get('enabled', False):
            try:
                handler = EmailAlertHandler(EmailConfig(**email_config))
                self.add_handler(handler.send_alert)
                logger.info("Email alert handler added")
            except Exception as e:
                logger.error(f"Failed to setup email handler: {e}")

        # Slack处理器
        slack_config = config_data.get('slack')
        if slack_config and slack_config.get('enabled', False):
            try:
                handler = SlackAlertHandler(SlackConfig(**slack_config))
                self.add_handler(handler.send_alert)
                logger.info("Slack alert handler added")
            except Exception as e:
                logger.error(f"Failed to setup Slack handler: {e}")

        # Webhook处理器
        webhook_config = config_data.get('webhook')
        if webhook_config and webhook_config.get('enabled', False):
            try:
                handler = WebhookAlertHandler(WebhookConfig(**webhook_config))
                self.add_handler(handler.send_alert)
                logger.info("Webhook alert handler added")
            except Exception as e:
                logger.error(f"Failed to setup webhook handler: {e}")

    def add_handler(self, handler: Callable[[Alert], bool]):
        """添加告警处理器"""
        self.handlers.append(handler)

    def handle_alert(self, alert: Alert) -> bool:
        """处理告警"""
        if not self.config.enabled:
            return False

        # 检查告警级别
        if alert.level.value < self.config.min_alert_level.value:
            return False

        # 检查冷却时间
        tags = alert.tags or {}
        alert_key = f"{alert.metric_type.value}:{tags.get('sla_target', 'unknown')}"
        last_sent = self.alert_history.get(alert_key)
        if last_sent:
            minutes_since_last = (datetime.now() - last_sent).total_seconds() / 60
            if minutes_since_last < self.config.cooldown_minutes:
                logger.debug(f"Alert {alert_key} in cooldown period")
                return False

        # 检查每小时限制
        recent_alerts = [
            t for t in self.alert_history.values()
            if (datetime.now() - t).total_seconds() < 3600
        ]
        if len(recent_alerts) >= self.config.max_alerts_per_hour:
            logger.warning("Alert rate limit exceeded")
            return False

        # 发送告警
        success_count = 0
        for handler in self.handlers:
            try:
                if handler(alert):
                    success_count += 1
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")

        # 记录发送时间
        if success_count > 0:
            self.alert_history[alert_key] = datetime.now()

        return success_count > 0

    def create_default_config(self):
        """创建默认配置文件"""
        default_config = {
            "enabled": True,
            "min_alert_level": "warning",
            "cooldown_minutes": 5,
            "max_alerts_per_hour": 20,
            "email": {
                "enabled": False,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "your-email@gmail.com",
                "password": "your-app-password",
                "use_tls": True,
                "from_email": "your-email@gmail.com",
                "to_emails": ["admin@example.com"]
            },
            "slack": {
                "enabled": False,
                "webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
                "channel": "#alerts",
                "username": "SLA Monitor",
                "icon_emoji": ":warning:"
            },
            "webhook": {
                "enabled": False,
                "url": "https://your-webhook-endpoint.com/alerts",
                "method": "POST",
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer YOUR_TOKEN"
                },
                "timeout": 10
            }
        }

        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(default_config, f, indent=2)

            logger.info(f"Default alert config created at {self.config_path}")

        except Exception as e:
            logger.error(f"Failed to create default config: {e}")


# 全局告警管理器
alert_manager = AlertManager()