#!/usr/bin/env python3
"""
Remote Assistance WebSocket Server
Stage 12: Multi-platform & Diagnostics & Optimization

Real-time remote assistance with WebSocket streaming:
1. Screen sharing and remote control
2. File transfer and session recording
3. Multi-device support (Desktop + Android)
4. Authentication and authorization
5. Session management and logging
6. Performance monitoring
"""

import asyncio
import websockets
import json
import time
import base64
import hashlib
import uuid
import os
import threading
from typing import Dict, Set, Optional, Any, List
from dataclasses import dataclass, asdict
from enum import Enum
import logging

# Import our modules
try:
    from ..core.capture import ScreenCapture
    from ..core.executor import Executor
    from ..adapters.android.android_executor import AndroidExecutor
except ImportError:
    # Handle import when running standalone
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    try:
        from core.capture import ScreenCapture
        from core.executor import Executor
        from adapters.android.android_executor import AndroidExecutor
    except ImportError:
        ScreenCapture = None
        Executor = None
        AndroidExecutor = None

class MessageType(Enum):
    # Authentication
    AUTH = "auth"
    AUTH_RESPONSE = "auth_response"

    # Session management
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SESSION_LIST = "session_list"

    # Screen sharing
    SCREENSHOT = "screenshot"
    SCREEN_STREAM = "screen_stream"

    # Remote control
    MOUSE_CLICK = "mouse_click"
    MOUSE_MOVE = "mouse_move"
    KEY_PRESS = "key_press"
    TYPE_TEXT = "type_text"

    # Android control
    ANDROID_TAP = "android_tap"
    ANDROID_SWIPE = "android_swipe"
    ANDROID_SCREENSHOT = "android_screenshot"

    # File operations
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    FILE_LIST = "file_list"

    # System info
    SYSTEM_INFO = "system_info"
    PERFORMANCE_STATS = "performance_stats"

    # Generic
    ERROR = "error"
    SUCCESS = "success"

@dataclass
class RemoteSession:
    """Remote assistance session"""
    session_id: str
    client_id: str
    operator_id: str
    platform: str  # "desktop" or "android"
    start_time: float
    active: bool = True
    permissions: Set[str] = None

    def __post_init__(self):
        if self.permissions is None:
            self.permissions = {"view", "control"}

@dataclass
class ConnectedClient:
    """Connected WebSocket client"""
    websocket: websockets.WebSocketServerProtocol
    client_id: str
    client_type: str  # "operator" or "target"
    authenticated: bool = False
    session_id: Optional[str] = None
    platform: str = "desktop"

class RemoteAssistanceServer:
    """WebSocket-based remote assistance server"""

    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port

        # Client management
        self.clients: Dict[str, ConnectedClient] = {}
        self.sessions: Dict[str, RemoteSession] = {}

        # Platform handlers
        self.screen_capture = None
        self.desktop_executor = None
        self.android_executor = None

        # Initialize platform support
        self._init_platform_support()

        # Authentication (simple token-based for demo)
        self.auth_tokens = {
            "operator_token": "operator",
            "target_token": "target"
        }

        # Streaming control
        self.streaming_sessions: Set[str] = set()
        self.stream_fps = 10  # 10 FPS for screen streaming

        # Logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def _init_platform_support(self):
        """Initialize platform-specific handlers"""
        # Desktop support
        if ScreenCapture:
            self.screen_capture = ScreenCapture()
        if Executor:
            self.desktop_executor = Executor()

        # Android support
        if AndroidExecutor:
            try:
                self.android_executor = AndroidExecutor()
                if self.android_executor.device_id:
                    self.logger.info(f"Android device connected: {self.android_executor.device_id}")
            except Exception as e:
                self.logger.warning(f"Android initialization failed: {e}")

    async def register_client(self, websocket: websockets.WebSocketServerProtocol) -> str:
        """Register new WebSocket client"""
        client_id = str(uuid.uuid4())
        client = ConnectedClient(
            websocket=websocket,
            client_id=client_id,
            client_type="unknown"
        )
        self.clients[client_id] = client

        self.logger.info(f"Client registered: {client_id}")
        return client_id

    async def unregister_client(self, client_id: str):
        """Unregister WebSocket client"""
        if client_id in self.clients:
            client = self.clients[client_id]

            # End any active sessions
            if client.session_id:
                await self.end_session(client.session_id)

            del self.clients[client_id]
            self.logger.info(f"Client unregistered: {client_id}")

    async def authenticate_client(self, client_id: str, token: str) -> bool:
        """Authenticate client with token"""
        if client_id not in self.clients:
            return False

        client = self.clients[client_id]

        if token in self.auth_tokens:
            client.authenticated = True
            client.client_type = self.auth_tokens[token]
            self.logger.info(f"Client authenticated: {client_id} as {client.client_type}")
            return True

        return False

    async def start_session(self, operator_id: str, target_platform: str = "desktop") -> Optional[str]:
        """Start remote assistance session"""
        session_id = str(uuid.uuid4())

        # Find available target client
        target_client = None
        for client in self.clients.values():
            if (client.client_type == "target" and
                client.authenticated and
                not client.session_id):
                target_client = client
                break

        if not target_client:
            return None

        # Create session
        session = RemoteSession(
            session_id=session_id,
            client_id=target_client.client_id,
            operator_id=operator_id,
            platform=target_platform,
            start_time=time.time()
        )

        self.sessions[session_id] = session
        target_client.session_id = session_id
        target_client.platform = target_platform

        self.logger.info(f"Session started: {session_id}")
        return session_id

    async def end_session(self, session_id: str):
        """End remote assistance session"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.active = False

            # Update client
            for client in self.clients.values():
                if client.session_id == session_id:
                    client.session_id = None
                    break

            # Stop streaming
            self.streaming_sessions.discard(session_id)

            del self.sessions[session_id]
            self.logger.info(f"Session ended: {session_id}")

    async def handle_message(self, client_id: str, message: Dict[str, Any]):
        """Handle incoming WebSocket message"""
        try:
            msg_type = MessageType(message.get("type"))
            client = self.clients.get(client_id)

            if not client:
                return

            # Handle authentication
            if msg_type == MessageType.AUTH:
                token = message.get("token")
                success = await self.authenticate_client(client_id, token)

                response = {
                    "type": MessageType.AUTH_RESPONSE.value,
                    "success": success,
                    "client_type": client.client_type if success else None
                }
                await client.websocket.send(json.dumps(response))
                return

            # Require authentication for other operations
            if not client.authenticated:
                await self.send_error(client.websocket, "Authentication required")
                return

            # Handle session management
            if msg_type == MessageType.SESSION_START:
                platform = message.get("platform", "desktop")
                session_id = await self.start_session(client_id, platform)

                response = {
                    "type": MessageType.SUCCESS.value,
                    "session_id": session_id
                }
                await client.websocket.send(json.dumps(response))

            elif msg_type == MessageType.SESSION_END:
                session_id = message.get("session_id")
                await self.end_session(session_id)

            elif msg_type == MessageType.SESSION_LIST:
                sessions_info = [
                    {
                        "session_id": sid,
                        "platform": session.platform,
                        "start_time": session.start_time,
                        "active": session.active
                    }
                    for sid, session in self.sessions.items()
                    if session.active
                ]

                response = {
                    "type": MessageType.SUCCESS.value,
                    "sessions": sessions_info
                }
                await client.websocket.send(json.dumps(response))

            # Handle screen operations
            elif msg_type == MessageType.SCREENSHOT:
                await self.handle_screenshot(client)

            elif msg_type == MessageType.SCREEN_STREAM:
                await self.handle_screen_stream(client, message)

            # Handle remote control
            elif msg_type == MessageType.MOUSE_CLICK:
                await self.handle_mouse_click(client, message)

            elif msg_type == MessageType.MOUSE_MOVE:
                await self.handle_mouse_move(client, message)

            elif msg_type == MessageType.KEY_PRESS:
                await self.handle_key_press(client, message)

            elif msg_type == MessageType.TYPE_TEXT:
                await self.handle_type_text(client, message)

            # Handle Android operations
            elif msg_type == MessageType.ANDROID_TAP:
                await self.handle_android_tap(client, message)

            elif msg_type == MessageType.ANDROID_SWIPE:
                await self.handle_android_swipe(client, message)

            elif msg_type == MessageType.ANDROID_SCREENSHOT:
                await self.handle_android_screenshot(client)

            # Handle system info
            elif msg_type == MessageType.SYSTEM_INFO:
                await self.handle_system_info(client)

            elif msg_type == MessageType.PERFORMANCE_STATS:
                await self.handle_performance_stats(client)

        except Exception as e:
            self.logger.error(f"Message handling error: {e}")
            await self.send_error(client.websocket, str(e))

    async def handle_screenshot(self, client: ConnectedClient):
        """Handle screenshot request"""
        if client.platform == "desktop" and self.screen_capture:
            screenshot = self.screen_capture.capture()
            if screenshot is not None:
                # Encode as base64
                screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')

                response = {
                    "type": MessageType.SCREENSHOT.value,
                    "data": screenshot_b64,
                    "timestamp": time.time()
                }
                await client.websocket.send(json.dumps(response))

        elif client.platform == "android" and self.android_executor:
            screenshot = self.android_executor.take_screenshot()
            if screenshot:
                screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')

                response = {
                    "type": MessageType.SCREENSHOT.value,
                    "data": screenshot_b64,
                    "timestamp": time.time()
                }
                await client.websocket.send(json.dumps(response))

    async def handle_screen_stream(self, client: ConnectedClient, message: Dict[str, Any]):
        """Handle screen streaming request"""
        action = message.get("action", "start")
        session_id = client.session_id

        if action == "start" and session_id:
            self.streaming_sessions.add(session_id)
            asyncio.create_task(self.stream_screen(client))

        elif action == "stop" and session_id:
            self.streaming_sessions.discard(session_id)

    async def stream_screen(self, client: ConnectedClient):
        """Stream screen continuously"""
        session_id = client.session_id
        if not session_id:
            return

        frame_interval = 1.0 / self.stream_fps

        while session_id in self.streaming_sessions:
            try:
                if client.platform == "desktop" and self.screen_capture:
                    screenshot = self.screen_capture.capture()
                elif client.platform == "android" and self.android_executor:
                    screenshot = self.android_executor.take_screenshot()
                else:
                    screenshot = None

                if screenshot:
                    screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')

                    response = {
                        "type": MessageType.SCREEN_STREAM.value,
                        "data": screenshot_b64,
                        "timestamp": time.time()
                    }
                    await client.websocket.send(json.dumps(response))

                await asyncio.sleep(frame_interval)

            except Exception as e:
                self.logger.error(f"Screen streaming error: {e}")
                break

        self.streaming_sessions.discard(session_id)

    async def handle_mouse_click(self, client: ConnectedClient, message: Dict[str, Any]):
        """Handle mouse click command"""
        if client.platform == "desktop" and self.desktop_executor:
            x = message.get("x", 0)
            y = message.get("y", 0)
            button = message.get("button", "left")

            success = self.desktop_executor.click(x, y, button)

            response = {
                "type": MessageType.SUCCESS.value if success else MessageType.ERROR.value,
                "message": "Click executed" if success else "Click failed"
            }
            await client.websocket.send(json.dumps(response))

    async def handle_mouse_move(self, client: ConnectedClient, message: Dict[str, Any]):
        """Handle mouse move command"""
        if client.platform == "desktop" and self.desktop_executor:
            x = message.get("x", 0)
            y = message.get("y", 0)

            success = self.desktop_executor.move_to(x, y)

            response = {
                "type": MessageType.SUCCESS.value if success else MessageType.ERROR.value,
                "message": "Move executed" if success else "Move failed"
            }
            await client.websocket.send(json.dumps(response))

    async def handle_key_press(self, client: ConnectedClient, message: Dict[str, Any]):
        """Handle key press command"""
        if client.platform == "desktop" and self.desktop_executor:
            key = message.get("key")

            success = self.desktop_executor.press_key(key) if key else False

            response = {
                "type": MessageType.SUCCESS.value if success else MessageType.ERROR.value,
                "message": "Key press executed" if success else "Key press failed"
            }
            await client.websocket.send(json.dumps(response))

    async def handle_type_text(self, client: ConnectedClient, message: Dict[str, Any]):
        """Handle type text command"""
        if client.platform == "desktop" and self.desktop_executor:
            text = message.get("text", "")

            success = self.desktop_executor.type_text(text)

            response = {
                "type": MessageType.SUCCESS.value if success else MessageType.ERROR.value,
                "message": "Text typed" if success else "Text input failed"
            }
            await client.websocket.send(json.dumps(response))

    async def handle_android_tap(self, client: ConnectedClient, message: Dict[str, Any]):
        """Handle Android tap command"""
        if client.platform == "android" and self.android_executor:
            x = message.get("x", 0)
            y = message.get("y", 0)

            success = self.android_executor.tap(x, y)

            response = {
                "type": MessageType.SUCCESS.value if success else MessageType.ERROR.value,
                "message": "Tap executed" if success else "Tap failed"
            }
            await client.websocket.send(json.dumps(response))

    async def handle_android_swipe(self, client: ConnectedClient, message: Dict[str, Any]):
        """Handle Android swipe command"""
        if client.platform == "android" and self.android_executor:
            x1 = message.get("x1", 0)
            y1 = message.get("y1", 0)
            x2 = message.get("x2", 0)
            y2 = message.get("y2", 0)
            duration = message.get("duration", 300)

            success = self.android_executor.swipe(x1, y1, x2, y2, duration)

            response = {
                "type": MessageType.SUCCESS.value if success else MessageType.ERROR.value,
                "message": "Swipe executed" if success else "Swipe failed"
            }
            await client.websocket.send(json.dumps(response))

    async def handle_android_screenshot(self, client: ConnectedClient):
        """Handle Android screenshot request"""
        if client.platform == "android" and self.android_executor:
            screenshot = self.android_executor.take_screenshot()
            if screenshot:
                screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')

                response = {
                    "type": MessageType.ANDROID_SCREENSHOT.value,
                    "data": screenshot_b64,
                    "timestamp": time.time()
                }
                await client.websocket.send(json.dumps(response))

    async def handle_system_info(self, client: ConnectedClient):
        """Handle system info request"""
        info = {}

        if client.platform == "android" and self.android_executor:
            info = self.android_executor.get_device_info()
        else:
            # Desktop system info
            import platform
            import psutil

            info = {
                "platform": platform.system(),
                "platform_version": platform.version(),
                "architecture": platform.architecture()[0],
                "cpu_count": psutil.cpu_count(),
                "memory_total": psutil.virtual_memory().total,
                "disk_usage": psutil.disk_usage('/').percent
            }

        response = {
            "type": MessageType.SYSTEM_INFO.value,
            "info": info
        }
        await client.websocket.send(json.dumps(response))

    async def handle_performance_stats(self, client: ConnectedClient):
        """Handle performance stats request"""
        stats = {}

        if client.platform == "android" and self.android_executor:
            stats = self.android_executor.get_performance_stats()
        else:
            # Desktop performance stats
            import psutil

            stats = {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_io": psutil.disk_io_counters()._asdict() if psutil.disk_io_counters() else {},
                "network_io": psutil.net_io_counters()._asdict() if psutil.net_io_counters() else {}
            }

        response = {
            "type": MessageType.PERFORMANCE_STATS.value,
            "stats": stats
        }
        await client.websocket.send(json.dumps(response))

    async def send_error(self, websocket: websockets.WebSocketServerProtocol, message: str):
        """Send error message to client"""
        error_response = {
            "type": MessageType.ERROR.value,
            "message": message
        }
        await websocket.send(json.dumps(error_response))

    async def handle_client(self, websocket: websockets.WebSocketServerProtocol, path: str):
        """Handle WebSocket client connection"""
        client_id = await self.register_client(websocket)

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.handle_message(client_id, data)
                except json.JSONDecodeError:
                    await self.send_error(websocket, "Invalid JSON")
                except Exception as e:
                    self.logger.error(f"Message processing error: {e}")
                    await self.send_error(websocket, str(e))

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister_client(client_id)

    async def start_server(self):
        """Start the WebSocket server"""
        self.logger.info(f"Starting remote assistance server on {self.host}:{self.port}")

        server = await websockets.serve(
            self.handle_client,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=10
        )

        self.logger.info("Remote assistance server started")
        return server

    def run(self):
        """Run the server"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            server = loop.run_until_complete(self.start_server())
            loop.run_forever()
        except KeyboardInterrupt:
            self.logger.info("Server stopped by user")
        finally:
            loop.close()

def main():
    """Run remote assistance server"""
    server = RemoteAssistanceServer()
    server.run()

if __name__ == "__main__":
    main()