import base64
import json
import os
import urllib.request
import urllib.error

# 配置
IMAGE_PATH = os.path.join(os.path.dirname(__file__), "s5.png")
API_URL = "http://127.0.0.1:11434/v1/chat/completions"
MODEL = "qwen2.5vl:latest"

def main():
    if not os.path.exists(IMAGE_PATH):
        print(f"Error: File not found at {IMAGE_PATH}")
        return

    # 1. 读取并编码图片
    try:
        with open(IMAGE_PATH, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Error reading image: {e}")
        return

    # 2. 构造请求 Payload
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text", 
                        "text": "请仔细观察这张图片，每个元素上都有数字,找到图片下面绿色的微信图标,图标为绿色,里面有两个白色气泡。请直接告诉我微信图标上面的数字"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 300
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(API_URL, data=data, headers={"Content-Type": "application/json"})

    # 3. 发送请求
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            content = result['choices'][0]['message']['content']
            print("-" * 20)
            print("LLM Response:")
            print(content)
            print("-" * 20)

    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} {e.reason}")
        print(e.read().decode('utf-8'))
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}")
    except Exception as e:
        print(f"Error communicating with LLM: {e}")

if __name__ == "__main__":
    main()