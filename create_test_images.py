#!/usr/bin/env python3
"""
创建用于端到端测试的模拟界面图片
"""

import cv2
import numpy as np
import base64
import json

def create_wechat_main_interface():
    """创建微信主界面模拟图"""
    img = np.ones((1572, 2888, 3), dtype=np.uint8) * 240  # 浅灰背景

    # 标题栏
    cv2.rectangle(img, (0, 0), (2888, 120), (30, 30, 30), -1)
    cv2.putText(img, "WeChat", (50, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2)

    # 搜索框
    search_box = (200, 150, 2400, 220)
    cv2.rectangle(img, (search_box[0], search_box[1]), (search_box[2], search_box[3]), (255, 255, 255), -1)
    cv2.rectangle(img, (search_box[0], search_box[1]), (search_box[2], search_box[3]), (200, 200, 200), 2)
    cv2.putText(img, "搜索", (250, 195), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (150, 150, 150), 2)

    # 搜索图标 (放大镜)
    cv2.circle(img, (2300, 185), 25, (100, 100, 100), 3)
    cv2.line(img, (2320, 205), (2340, 225), (100, 100, 100), 3)

    # 一些聊天项目
    for i in range(5):
        y_start = 280 + i * 100
        cv2.rectangle(img, (100, y_start), (2700, y_start + 80), (255, 255, 255), -1)
        cv2.putText(img, f"联系人 {i+1}", (150, y_start + 45), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (50, 50, 50), 2)

    return img

def create_browser_search_page():
    """创建浏览器搜索页面模拟图"""
    img = np.ones((1440, 2560, 3), dtype=np.uint8) * 250  # 白色背景

    # 浏览器地址栏
    cv2.rectangle(img, (0, 0), (2560, 80), (240, 240, 240), -1)
    cv2.putText(img, "https://www.xiaohongshu.com", (50, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (50, 50, 50), 2)

    # 页面标题
    cv2.putText(img, "小红书", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 50, 50), 3)

    # 搜索框
    search_box = (300, 200, 2000, 270)
    cv2.rectangle(img, (search_box[0], search_box[1]), (search_box[2], search_box[3]), (255, 255, 255), -1)
    cv2.rectangle(img, (search_box[0], search_box[1]), (search_box[2], search_box[3]), (200, 200, 200), 2)
    cv2.putText(img, "Search or type something...", (350, 245), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (150, 150, 150), 2)

    # 搜索按钮
    search_btn = (2050, 200, 2200, 270)
    cv2.rectangle(img, (search_btn[0], search_btn[1]), (search_btn[2], search_btn[3]), (255, 100, 100), -1)
    cv2.putText(img, "搜索", (2080, 245), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    # 一些内容区域
    for i in range(3):
        for j in range(4):
            x = 200 + j * 500
            y = 350 + i * 300
            cv2.rectangle(img, (x, y), (x + 400, y + 250), (245, 245, 245), -1)
            cv2.rectangle(img, (x, y), (x + 400, y + 250), (200, 200, 200), 1)
            cv2.putText(img, f"内容 {i*4+j+1}", (x + 150, y + 130), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (80, 80, 80), 2)

    return img

def create_login_page():
    """创建登录页面模拟图"""
    img = np.ones((1080, 1920, 3), dtype=np.uint8) * 250  # 白色背景

    # 标题
    cv2.putText(img, "Login", (800, 200), cv2.FONT_HERSHEY_SIMPLEX, 3.0, (50, 50, 50), 4)

    # 用户名输入框
    username_box = (400, 350, 1520, 420)
    cv2.rectangle(img, (username_box[0], username_box[1]), (username_box[2], username_box[3]), (255, 255, 255), -1)
    cv2.rectangle(img, (username_box[0], username_box[1]), (username_box[2], username_box[3]), (200, 200, 200), 2)
    cv2.putText(img, "Username", (450, 395), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (150, 150, 150), 2)

    # 密码输入框
    password_box = (400, 480, 1520, 550)
    cv2.rectangle(img, (password_box[0], password_box[1]), (password_box[2], password_box[3]), (255, 255, 255), -1)
    cv2.rectangle(img, (password_box[0], password_box[1]), (password_box[2], password_box[3]), (200, 200, 200), 2)
    cv2.putText(img, "Password", (450, 525), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (150, 150, 150), 2)

    # 登录按钮
    login_btn = (700, 620, 1220, 690)
    cv2.rectangle(img, (login_btn[0], login_btn[1]), (login_btn[2], login_btn[3]), (50, 150, 250), -1)
    cv2.putText(img, "登录", (860, 665), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
    cv2.putText(img, "Sign in", (810, 720), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (100, 100, 100), 2)

    return img

def image_to_base64(img, format='png'):
    """将OpenCV图像转换为base64"""
    success, encoded = cv2.imencode(f'.{format}', img)
    if success:
        return base64.b64encode(encoded.tobytes()).decode('utf-8')
    return None

def main():
    """生成测试图片并保存base64"""

    # 创建测试图片
    wechat_img = create_wechat_main_interface()
    browser_img = create_browser_search_page()
    login_img = create_login_page()

    # 保存为文件
    cv2.imwrite('test_wechat.png', wechat_img)
    cv2.imwrite('test_browser.png', browser_img)
    cv2.imwrite('test_login.png', login_img)

    # 转换为base64并保存
    test_data = {
        "wechat_main": {
            "base64": image_to_base64(wechat_img),
            "screen_size": [2888, 1572],
            "description": "微信主界面，包含搜索框和搜索图标"
        },
        "browser_search": {
            "base64": image_to_base64(browser_img),
            "screen_size": [2560, 1440],
            "description": "浏览器搜索页面，包含搜索输入框和搜索按钮"
        },
        "login_page": {
            "base64": image_to_base64(login_img),
            "screen_size": [1920, 1080],
            "description": "登录页面，包含用户名输入框和登录按钮"
        }
    }

    with open('test_images_data.json', 'w', encoding='utf-8') as f:
        json.dump(test_data, f, indent=2, ensure_ascii=False)

    print("✅ 测试图片已生成:")
    print(f"   - test_wechat.png: 微信主界面 ({wechat_img.shape[1]}x{wechat_img.shape[0]})")
    print(f"   - test_browser.png: 浏览器页面 ({browser_img.shape[1]}x{browser_img.shape[0]})")
    print(f"   - test_login.png: 登录页面 ({login_img.shape[1]}x{login_img.shape[0]})")
    print("   - test_images_data.json: Base64数据文件")

if __name__ == "__main__":
    main()