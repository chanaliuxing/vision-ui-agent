# client/login_ui.py
import requests
import json
import getpass
from pathlib import Path

def login_and_save(api_base):
    """CLI登录界面，保存认证信息"""
    print("=== AutoAgent Login ===")

    # 检查是否已有保存的认证信息
    auth_file = Path.home() / ".autoagent" / "auth.json"
    if auth_file.exists():
        try:
            auth_data = json.loads(auth_file.read_text(encoding="utf-8"))
            if auth_data.get("access_token"):
                print("Found existing authentication token")
                return auth_data["access_token"]
        except Exception:
            pass

    # 获取登录凭据
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")

    if not email or not password:
        print("Email and password are required")
        return None

    try:
        response = requests.post(
            f"{api_base}/auth/login",
            json={"email": email, "password": password},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        # 保存认证信息
        auth_file.parent.mkdir(parents=True, exist_ok=True)
        auth_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        print(f"Login successful! Welcome, {data['user']['email']}")
        return data["access_token"]

    except requests.exceptions.RequestException as e:
        print(f"Login failed: {e}")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def register_user(api_base):
    """用户注册"""
    print("=== AutoAgent Registration ===")

    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")
    confirm_password = getpass.getpass("Confirm Password: ")

    if not email or not password:
        print("Email and password are required")
        return False

    if password != confirm_password:
        print("Passwords do not match")
        return False

    try:
        response = requests.post(
            f"{api_base}/auth/register",
            json={"email": email, "password": password},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        print(f"Registration successful! User created: {data['user']['email']}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"Registration failed: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False