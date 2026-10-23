#!/usr/bin/env python3
"""
Android Automation Adapter
Stage 12: Multi-platform & Diagnostics & Optimization

Android automation using ADB and UI Automator:
1. ADB bridge for device communication
2. UI element detection via XML dump
3. Touch, swipe, and input gestures
4. App management and installation
5. Screenshot and device mirroring
6. Performance monitoring
"""

import subprocess
import time
import xml.etree.ElementTree as ET
import re
import json
import os
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import threading
import base64

class DeviceState(Enum):
    UNKNOWN = "unknown"
    DEVICE = "device"
    OFFLINE = "offline"
    UNAUTHORIZED = "unauthorized"
    BOOTLOADER = "bootloader"
    RECOVERY = "recovery"

@dataclass
class AndroidDevice:
    """Android device information"""
    device_id: str
    state: DeviceState
    model: str = ""
    android_version: str = ""
    api_level: int = 0
    resolution: Tuple[int, int] = (0, 0)
    density: int = 0

@dataclass
class UIElement:
    """UI element representation"""
    bounds: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    text: str = ""
    content_desc: str = ""
    resource_id: str = ""
    class_name: str = ""
    package: str = ""
    clickable: bool = False
    scrollable: bool = False
    checkable: bool = False
    checked: bool = False
    enabled: bool = True

class AndroidExecutor:
    """Android automation executor using ADB"""

    def __init__(self, device_id: str = None):
        self.device_id = device_id
        self.device_info: Optional[AndroidDevice] = None
        self.screenshot_cache: Dict[str, bytes] = {}

        # Check ADB availability
        self._check_adb()

        # Auto-select device if not specified
        if not self.device_id:
            self.device_id = self._auto_select_device()

        if self.device_id:
            self._initialize_device()

    def _check_adb(self) -> bool:
        """Check if ADB is available"""
        try:
            result = subprocess.run(['adb', 'version'],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print("✅ ADB available")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        print("❌ ADB not found. Please install Android SDK Platform Tools")
        return False

    def _run_adb(self, command: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """Run ADB command with device specification"""
        if self.device_id:
            cmd = ['adb', '-s', self.device_id] + command
        else:
            cmd = ['adb'] + command

        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def _auto_select_device(self) -> Optional[str]:
        """Auto-select the first available device"""
        devices = self.list_devices()
        if devices:
            available = [d for d in devices if d.state == DeviceState.DEVICE]
            if available:
                print(f"Auto-selected device: {available[0].device_id}")
                return available[0].device_id
        return None

    def _initialize_device(self):
        """Initialize device information"""
        if not self.device_id:
            return

        try:
            # Get device info
            model = self._get_property('ro.product.model')
            version = self._get_property('ro.build.version.release')
            api_level = int(self._get_property('ro.build.version.sdk'))

            # Get screen dimensions
            result = self._run_adb(['shell', 'wm', 'size'])
            resolution_match = re.search(r'(\d+)x(\d+)', result.stdout)
            resolution = (int(resolution_match.group(1)), int(resolution_match.group(2))) if resolution_match else (0, 0)

            # Get density
            result = self._run_adb(['shell', 'wm', 'density'])
            density_match = re.search(r'(\d+)', result.stdout)
            density = int(density_match.group(1)) if density_match else 0

            self.device_info = AndroidDevice(
                device_id=self.device_id,
                state=DeviceState.DEVICE,
                model=model,
                android_version=version,
                api_level=api_level,
                resolution=resolution,
                density=density
            )

            print(f"✅ Device initialized: {model} (Android {version})")

        except Exception as e:
            print(f"⚠️  Device initialization partial: {e}")

    def _get_property(self, prop: str) -> str:
        """Get Android system property"""
        result = self._run_adb(['shell', 'getprop', prop])
        return result.stdout.strip()

    def list_devices(self) -> List[AndroidDevice]:
        """List all connected devices"""
        devices = []
        try:
            result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=10)
            lines = result.stdout.split('\n')[1:]  # Skip header

            for line in lines:
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        device_id = parts[0]
                        state_str = parts[1]

                        try:
                            state = DeviceState(state_str)
                        except ValueError:
                            state = DeviceState.UNKNOWN

                        devices.append(AndroidDevice(device_id=device_id, state=state))

        except Exception as e:
            print(f"Failed to list devices: {e}")

        return devices

    def take_screenshot(self, save_path: str = None) -> Optional[bytes]:
        """Take device screenshot"""
        if not self.device_id:
            return None

        try:
            # Take screenshot on device
            result = self._run_adb(['shell', 'screencap', '-p', '/sdcard/screenshot.png'])
            if result.returncode != 0:
                return None

            # Pull screenshot from device
            result = self._run_adb(['exec-out', 'cat', '/sdcard/screenshot.png'])
            if result.returncode != 0:
                return None

            screenshot_data = result.stdout.encode('latin-1')

            # Save if path provided
            if save_path:
                with open(save_path, 'wb') as f:
                    f.write(screenshot_data)

            # Cache screenshot
            self.screenshot_cache['latest'] = screenshot_data
            return screenshot_data

        except Exception as e:
            print(f"Screenshot failed: {e}")
            return None

    def get_ui_dump(self) -> Optional[str]:
        """Get UI hierarchy XML dump"""
        if not self.device_id:
            return None

        try:
            # Dump UI hierarchy
            result = self._run_adb(['shell', 'uiautomator', 'dump', '/sdcard/ui_dump.xml'])
            if result.returncode != 0:
                return None

            # Get the XML content
            result = self._run_adb(['shell', 'cat', '/sdcard/ui_dump.xml'])
            if result.returncode == 0:
                return result.stdout

        except Exception as e:
            print(f"UI dump failed: {e}")

        return None

    def parse_ui_elements(self, xml_content: str) -> List[UIElement]:
        """Parse UI elements from XML dump"""
        elements = []
        try:
            root = ET.fromstring(xml_content)

            for node in root.iter():
                if node.tag == 'node':
                    attrs = node.attrib

                    # Parse bounds
                    bounds_str = attrs.get('bounds', '[0,0][0,0]')
                    bounds_match = re.findall(r'\[(\d+),(\d+)\]', bounds_str)
                    if len(bounds_match) >= 2:
                        x1, y1 = map(int, bounds_match[0])
                        x2, y2 = map(int, bounds_match[1])
                        bounds = (x1, y1, x2, y2)
                    else:
                        bounds = (0, 0, 0, 0)

                    element = UIElement(
                        bounds=bounds,
                        text=attrs.get('text', ''),
                        content_desc=attrs.get('content-desc', ''),
                        resource_id=attrs.get('resource-id', ''),
                        class_name=attrs.get('class', ''),
                        package=attrs.get('package', ''),
                        clickable=attrs.get('clickable', 'false').lower() == 'true',
                        scrollable=attrs.get('scrollable', 'false').lower() == 'true',
                        checkable=attrs.get('checkable', 'false').lower() == 'true',
                        checked=attrs.get('checked', 'false').lower() == 'true',
                        enabled=attrs.get('enabled', 'true').lower() == 'true'
                    )

                    elements.append(element)

        except Exception as e:
            print(f"UI parsing failed: {e}")

        return elements

    def find_elements(self, text: str = None, content_desc: str = None,
                     resource_id: str = None, class_name: str = None) -> List[UIElement]:
        """Find UI elements by various criteria"""
        xml_content = self.get_ui_dump()
        if not xml_content:
            return []

        all_elements = self.parse_ui_elements(xml_content)
        matched_elements = []

        for element in all_elements:
            match = True

            if text and text not in element.text:
                match = False
            if content_desc and content_desc not in element.content_desc:
                match = False
            if resource_id and resource_id not in element.resource_id:
                match = False
            if class_name and class_name not in element.class_name:
                match = False

            if match:
                matched_elements.append(element)

        return matched_elements

    def tap(self, x: int, y: int) -> bool:
        """Tap at coordinates"""
        if not self.device_id:
            return False

        try:
            result = self._run_adb(['shell', 'input', 'tap', str(x), str(y)])
            return result.returncode == 0
        except Exception as e:
            print(f"Tap failed: {e}")
            return False

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> bool:
        """Swipe from one point to another"""
        if not self.device_id:
            return False

        try:
            result = self._run_adb(['shell', 'input', 'swipe',
                                 str(x1), str(y1), str(x2), str(y2), str(duration)])
            return result.returncode == 0
        except Exception as e:
            print(f"Swipe failed: {e}")
            return False

    def type_text(self, text: str) -> bool:
        """Type text (ASCII characters only)"""
        if not self.device_id:
            return False

        try:
            # Escape special characters
            escaped_text = text.replace(' ', '%s').replace('&', '\\&')
            result = self._run_adb(['shell', 'input', 'text', escaped_text])
            return result.returncode == 0
        except Exception as e:
            print(f"Text input failed: {e}")
            return False

    def press_key(self, keycode: str) -> bool:
        """Press a key (e.g., KEYCODE_HOME, KEYCODE_BACK)"""
        if not self.device_id:
            return False

        try:
            result = self._run_adb(['shell', 'input', 'keyevent', keycode])
            return result.returncode == 0
        except Exception as e:
            print(f"Key press failed: {e}")
            return False

    def click_element(self, element: UIElement) -> bool:
        """Click on a UI element"""
        x1, y1, x2, y2 = element.bounds
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        return self.tap(center_x, center_y)

    def scroll_down(self, steps: int = 3) -> bool:
        """Scroll down on screen"""
        if not self.device_info:
            return False

        width, height = self.device_info.resolution
        start_x = width // 2
        start_y = int(height * 0.8)
        end_x = width // 2
        end_y = int(height * 0.2)

        for _ in range(steps):
            if not self.swipe(start_x, start_y, end_x, end_y):
                return False
            time.sleep(0.5)

        return True

    def scroll_up(self, steps: int = 3) -> bool:
        """Scroll up on screen"""
        if not self.device_info:
            return False

        width, height = self.device_info.resolution
        start_x = width // 2
        start_y = int(height * 0.2)
        end_x = width // 2
        end_y = int(height * 0.8)

        for _ in range(steps):
            if not self.swipe(start_x, start_y, end_x, end_y):
                return False
            time.sleep(0.5)

        return True

    def launch_app(self, package_name: str, activity: str = None) -> bool:
        """Launch an app"""
        if not self.device_id:
            return False

        try:
            if activity:
                component = f"{package_name}/{activity}"
            else:
                component = package_name

            result = self._run_adb(['shell', 'am', 'start', '-n', component])
            return result.returncode == 0
        except Exception as e:
            print(f"App launch failed: {e}")
            return False

    def close_app(self, package_name: str) -> bool:
        """Force close an app"""
        if not self.device_id:
            return False

        try:
            result = self._run_adb(['shell', 'am', 'force-stop', package_name])
            return result.returncode == 0
        except Exception as e:
            print(f"App close failed: {e}")
            return False

    def install_apk(self, apk_path: str) -> bool:
        """Install APK file"""
        if not self.device_id:
            return False

        try:
            result = self._run_adb(['install', apk_path], timeout=120)
            return result.returncode == 0
        except Exception as e:
            print(f"APK install failed: {e}")
            return False

    def uninstall_app(self, package_name: str) -> bool:
        """Uninstall an app"""
        if not self.device_id:
            return False

        try:
            result = self._run_adb(['uninstall', package_name])
            return result.returncode == 0
        except Exception as e:
            print(f"App uninstall failed: {e}")
            return False

    def get_current_activity(self) -> Optional[str]:
        """Get current foreground activity"""
        if not self.device_id:
            return None

        try:
            result = self._run_adb(['shell', 'dumpsys', 'activity', 'activities'])
            if result.returncode == 0:
                # Parse activity from dumpsys output
                for line in result.stdout.split('\n'):
                    if 'mResumedActivity' in line:
                        match = re.search(r'ActivityRecord{[^}]*}\s+([^\s]+)', line)
                        if match:
                            return match.group(1)
        except Exception as e:
            print(f"Get activity failed: {e}")

        return None

    def wait_for_element(self, text: str = None, content_desc: str = None,
                        resource_id: str = None, timeout: int = 10) -> Optional[UIElement]:
        """Wait for element to appear"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            elements = self.find_elements(text=text, content_desc=content_desc,
                                        resource_id=resource_id)
            if elements:
                return elements[0]
            time.sleep(1)

        return None

    def get_device_info(self) -> Dict[str, Any]:
        """Get comprehensive device information"""
        if not self.device_info:
            return {}

        return {
            'device_id': self.device_info.device_id,
            'model': self.device_info.model,
            'android_version': self.device_info.android_version,
            'api_level': self.device_info.api_level,
            'resolution': self.device_info.resolution,
            'density': self.device_info.density,
            'state': self.device_info.state.value
        }

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get device performance statistics"""
        if not self.device_id:
            return {}

        stats = {}
        try:
            # CPU usage
            result = self._run_adb(['shell', 'cat', '/proc/loadavg'])
            if result.returncode == 0:
                load_avg = result.stdout.strip().split()[:3]
                stats['cpu_load'] = [float(x) for x in load_avg]

            # Memory usage
            result = self._run_adb(['shell', 'cat', '/proc/meminfo'])
            if result.returncode == 0:
                mem_info = {}
                for line in result.stdout.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        mem_info[key.strip()] = value.strip()
                stats['memory'] = mem_info

            # Battery level
            result = self._run_adb(['shell', 'dumpsys', 'battery'])
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'level:' in line:
                        level = re.search(r'level:\s*(\d+)', line)
                        if level:
                            stats['battery_level'] = int(level.group(1))

        except Exception as e:
            print(f"Performance stats failed: {e}")

        return stats

    def enable_developer_options(self) -> bool:
        """Enable developer options if not already enabled"""
        if not self.device_id:
            return False

        try:
            # This requires user interaction, so just return status
            result = self._run_adb(['shell', 'settings', 'get', 'global', 'development_settings_enabled'])
            return result.stdout.strip() == '1'
        except Exception:
            return False