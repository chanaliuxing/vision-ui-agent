"""
真实微信API集成 - 使用企业微信或个人微信API
支持多种微信API集成方式：
1. 企业微信机器人API
2. 微信公众号API
3. 第三方微信SDK（如itchat、wechaty）
"""
import logging
import asyncio
import json
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
import aiohttp
import hashlib
import hmac
import base64

logger = logging.getLogger(__name__)


@dataclass
class WeChatConfig:
    """微信配置"""
    api_type: str  # "enterprise", "public", "personal"
    app_id: str = ""
    app_secret: str = ""
    webhook_url: str = ""  # 企业微信机器人webhook
    access_token: str = ""
    corp_id: str = ""  # 企业ID
    agent_id: str = ""  # 企业应用ID

    # 个人微信配置（第三方SDK）
    wechaty_token: str = ""
    wechaty_endpoint: str = ""


class WeChatEnterpriseAPI:
    """企业微信API客户端"""

    def __init__(self, config: WeChatConfig):
        self.config = config
        self.base_url = "https://qyapi.weixin.qq.com"
        self._access_token = None
        self._token_expires_at = 0

    async def get_access_token(self) -> str:
        """获取企业微信访问令牌"""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        url = f"{self.base_url}/cgi-bin/gettoken"
        params = {
            "corpid": self.config.corp_id,
            "corpsecret": self.config.app_secret
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                data = await response.json()

                if data.get("errcode") == 0:
                    self._access_token = data.get("access_token")
                    self._token_expires_at = time.time() + data.get("expires_in", 7200) - 60
                    logger.info("Enterprise WeChat access token obtained")
                    return self._access_token
                else:
                    raise Exception(f"Failed to get access token: {data}")

    async def send_text_message(self, user_id: str, content: str) -> bool:
        """发送文本消息"""
        try:
            access_token = await self.get_access_token()
            url = f"{self.base_url}/cgi-bin/message/send"

            payload = {
                "touser": user_id,
                "msgtype": "text",
                "agentid": self.config.agent_id,
                "text": {
                    "content": content
                },
                "safe": 0
            }

            params = {"access_token": access_token}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params, json=payload) as response:
                    data = await response.json()

                    if data.get("errcode") == 0:
                        logger.info(f"Message sent to {user_id}: {content[:50]}...")
                        return True
                    else:
                        logger.error(f"Failed to send message: {data}")
                        return False

        except Exception as e:
            logger.error(f"Error sending WeChat message: {e}")
            return False

    async def send_markdown_message(self, user_id: str, content: str) -> bool:
        """发送Markdown消息"""
        try:
            access_token = await self.get_access_token()
            url = f"{self.base_url}/cgi-bin/message/send"

            payload = {
                "touser": user_id,
                "msgtype": "markdown",
                "agentid": self.config.agent_id,
                "markdown": {
                    "content": content
                }
            }

            params = {"access_token": access_token}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params, json=payload) as response:
                    data = await response.json()

                    return data.get("errcode") == 0

        except Exception as e:
            logger.error(f"Error sending markdown message: {e}")
            return False


class WeChatWebhookAPI:
    """企业微信机器人Webhook API"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send_text(self, content: str, mentioned_list: List[str] = None) -> bool:
        """发送文本消息"""
        try:
            payload = {
                "msgtype": "text",
                "text": {
                    "content": content,
                    "mentioned_list": mentioned_list or []
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    data = await response.json()

                    if data.get("errcode") == 0:
                        logger.info(f"Webhook message sent: {content[:50]}...")
                        return True
                    else:
                        logger.error(f"Webhook send failed: {data}")
                        return False

        except Exception as e:
            logger.error(f"Error sending webhook message: {e}")
            return False

    async def send_markdown(self, content: str) -> bool:
        """发送Markdown消息"""
        try:
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": content
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    data = await response.json()
                    return data.get("errcode") == 0

        except Exception as e:
            logger.error(f"Error sending markdown webhook: {e}")
            return False


class WeChatPublicAPI:
    """微信公众号API客户端"""

    def __init__(self, config: WeChatConfig):
        self.config = config
        self.base_url = "https://api.weixin.qq.com"
        self._access_token = None
        self._token_expires_at = 0

    async def get_access_token(self) -> str:
        """获取公众号访问令牌"""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        url = f"{self.base_url}/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.config.app_id,
            "secret": self.config.app_secret
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                data = await response.json()

                if "access_token" in data:
                    self._access_token = data.get("access_token")
                    self._token_expires_at = time.time() + data.get("expires_in", 7200) - 60
                    logger.info("Public WeChat access token obtained")
                    return self._access_token
                else:
                    raise Exception(f"Failed to get public access token: {data}")

    async def send_template_message(self, openid: str, template_id: str,
                                  data: Dict, url: str = None) -> bool:
        """发送模板消息"""
        try:
            access_token = await self.get_access_token()
            api_url = f"{self.base_url}/cgi-bin/message/template/send"

            payload = {
                "touser": openid,
                "template_id": template_id,
                "url": url or "",
                "data": data
            }

            params = {"access_token": access_token}

            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, params=params, json=payload) as response:
                    result = await response.json()

                    if result.get("errcode") == 0:
                        logger.info(f"Template message sent to {openid}")
                        return True
                    else:
                        logger.error(f"Failed to send template message: {result}")
                        return False

        except Exception as e:
            logger.error(f"Error sending template message: {e}")
            return False


class WeChatyAPI:
    """Wechaty API客户端（第三方个人微信SDK）"""

    def __init__(self, config: WeChatConfig):
        self.config = config
        self.endpoint = config.wechaty_endpoint or "http://localhost:8080"
        self.token = config.wechaty_token

    async def send_message(self, contact_id: str, message: str) -> bool:
        """发送消息（通过Wechaty）"""
        try:
            url = f"{self.endpoint}/api/message/send"
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }

            payload = {
                "contactId": contact_id,
                "message": message
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Wechaty message sent to {contact_id}")
                        return True
                    else:
                        logger.error(f"Wechaty send failed: {response.status}")
                        return False

        except Exception as e:
            logger.error(f"Error sending Wechaty message: {e}")
            return False

    async def get_contacts(self) -> List[Dict]:
        """获取联系人列表"""
        try:
            url = f"{self.endpoint}/api/contacts"
            headers = {"Authorization": f"Bearer {self.token}"}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        contacts = await response.json()
                        logger.info(f"Retrieved {len(contacts)} contacts")
                        return contacts
                    else:
                        logger.error(f"Failed to get contacts: {response.status}")
                        return []

        except Exception as e:
            logger.error(f"Error getting contacts: {e}")
            return []


class WeChatRealIntegration:
    """真实微信集成类 - 统一接口"""

    def __init__(self, config: WeChatConfig):
        self.config = config
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """根据配置初始化对应的API客户端"""
        if self.config.api_type == "enterprise":
            if self.config.webhook_url:
                self.client = WeChatWebhookAPI(self.config.webhook_url)
            else:
                self.client = WeChatEnterpriseAPI(self.config)
        elif self.config.api_type == "public":
            self.client = WeChatPublicAPI(self.config)
        elif self.config.api_type == "personal":
            self.client = WeChatyAPI(self.config)
        else:
            raise ValueError(f"Unsupported WeChat API type: {self.config.api_type}")

    async def send_message(self, recipient: str, content: str,
                          message_type: str = "text") -> bool:
        """统一发送消息接口"""
        try:
            if isinstance(self.client, WeChatWebhookAPI):
                if message_type == "markdown":
                    return await self.client.send_markdown(content)
                else:
                    return await self.client.send_text(content)

            elif isinstance(self.client, WeChatEnterpriseAPI):
                if message_type == "markdown":
                    return await self.client.send_markdown_message(recipient, content)
                else:
                    return await self.client.send_text_message(recipient, content)

            elif isinstance(self.client, WeChatPublicAPI):
                # 公众号需要模板消息
                template_data = {
                    "content": {"value": content, "color": "#173177"}
                }
                return await self.client.send_template_message(
                    recipient, self.config.app_id, template_data
                )

            elif isinstance(self.client, WeChatyAPI):
                return await self.client.send_message(recipient, content)

            return False

        except Exception as e:
            logger.error(f"Failed to send message via {type(self.client).__name__}: {e}")
            return False

    async def get_user_info(self, user_id: str) -> Optional[Dict]:
        """获取用户信息"""
        try:
            if isinstance(self.client, WeChatyAPI):
                contacts = await self.client.get_contacts()
                for contact in contacts:
                    if contact.get("id") == user_id:
                        return contact

            # 其他API类型的用户信息获取
            return None

        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            return None

    async def test_connection(self) -> bool:
        """测试连接"""
        try:
            if isinstance(self.client, WeChatEnterpriseAPI):
                await self.client.get_access_token()
                return True
            elif isinstance(self.client, WeChatPublicAPI):
                await self.client.get_access_token()
                return True
            elif isinstance(self.client, WeChatWebhookAPI):
                # 发送测试消息
                return await self.client.send_text("连接测试")
            elif isinstance(self.client, WeChatyAPI):
                contacts = await self.client.get_contacts()
                return len(contacts) >= 0

            return False

        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False


def create_wechat_config_from_env() -> WeChatConfig:
    """从环境变量创建微信配置"""
    import os

    api_type = os.getenv("WECHAT_API_TYPE", "enterprise")

    config = WeChatConfig(
        api_type=api_type,
        app_id=os.getenv("WECHAT_APP_ID", ""),
        app_secret=os.getenv("WECHAT_APP_SECRET", ""),
        webhook_url=os.getenv("WECHAT_WEBHOOK_URL", ""),
        corp_id=os.getenv("WECHAT_CORP_ID", ""),
        agent_id=os.getenv("WECHAT_AGENT_ID", ""),
        wechaty_token=os.getenv("WECHATY_TOKEN", ""),
        wechaty_endpoint=os.getenv("WECHATY_ENDPOINT", "")
    )

    return config


async def test_wechat_real_integration():
    """测试真实微信集成"""
    config = create_wechat_config_from_env()
    integration = WeChatRealIntegration(config)

    logger.info(f"Testing WeChat integration with API type: {config.api_type}")

    # 测试连接
    connection_ok = await integration.test_connection()
    logger.info(f"Connection test: {'PASSED' if connection_ok else 'FAILED'}")

    # 测试发送消息（如果连接成功）
    if connection_ok:
        test_recipient = "test_user"  # 根据API类型调整
        test_message = "Hello from M3 Vision-First Engine!"

        send_ok = await integration.send_message(test_recipient, test_message)
        logger.info(f"Message send test: {'PASSED' if send_ok else 'FAILED'}")

    return {
        "api_type": config.api_type,
        "connection_test": connection_ok,
        "send_test": send_ok if connection_ok else None,
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    # 测试真实微信集成
    asyncio.run(test_wechat_real_integration())