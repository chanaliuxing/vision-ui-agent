#!/usr/bin/env python3
"""
端到端真实测试脚本 - 按照用户提供的测试方案
测试YOLO+LLM决策服务的完整链路
"""

import requests
import json
import base64
import time
from typing import Dict, Any, Optional

def load_test_images():
    """加载测试图片数据"""
    try:
        with open('test_images_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ 测试图片数据文件不存在，请先运行 create_test_images.py")
        return None

def make_request(url: str, payload: Dict[str, Any], timeout: int = 45) -> Optional[Dict[str, Any]]:
    """发送HTTP请求并处理响应"""
    try:
        print(f"📤 发送请求到 {url}")
        print(f"📊 请求大小: ~{len(json.dumps(payload))//1024}KB")

        start_time = time.time()
        resp = requests.post(url, json=payload, timeout=timeout)
        elapsed = time.time() - start_time

        print(f"📨 响应状态: {resp.status_code} ({elapsed:.1f}s)")

        if resp.status_code == 200:
            result = resp.json()
            return result
        else:
            print(f"❌ HTTP错误 {resp.status_code}: {resp.text[:500]}...")
            return None

    except requests.exceptions.Timeout:
        print(f"❌ 请求超时 (>{timeout}s)")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求异常: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析失败: {e}")
        return None

def analyze_response(result: Dict[str, Any], test_name: str) -> Dict[str, Any]:
    """分析响应结果"""
    analysis = {
        "test_name": test_name,
        "success": result.get('ok', False),
        "has_decision": False,
        "has_anchor": False,
        "has_verification_plan": False,
        "telemetry": {},
        "errors": []
    }

    if not analysis["success"]:
        error = result.get('error', {})
        analysis["errors"].append(f"API错误: {error.get('message', 'Unknown')}")
        return analysis

    data = result.get('data', {})

    # 检查决策
    decision = data.get('decision', {})
    if decision:
        analysis["has_decision"] = True
        analysis["decision"] = {
            "action": decision.get('action'),
            "confidence": decision.get('confidence', 0),
            "point": decision.get('point_in_capture', []),
            "bbox": decision.get('bbox_in_capture'),
            "reason_preview": decision.get('reason', '')[:100] + "..." if decision.get('reason') else ""
        }

        # 检查是否有NoneType.lower()错误
        reason = decision.get('reason', '')
        if 'NoneType' in reason:
            analysis["errors"].append("发现NoneType错误在reason中")
    else:
        analysis["errors"].append("缺少decision字段")

    # 检查锚点
    anchor_proposal = data.get('anchor_proposal')
    if anchor_proposal:
        analysis["has_anchor"] = True
        analysis["anchor_id"] = anchor_proposal.get('id')

    # 检查验证计划
    verification_plan = data.get('verification_plan')
    if verification_plan:
        analysis["has_verification_plan"] = True

    # 检查坐标映射
    mapping_hint = data.get('mapping_hint', {})
    analysis["mapping_hint"] = mapping_hint

    # 检查遥测数据
    telemetry = data.get('telemetry', {})
    analysis["telemetry"] = {
        "req_id": telemetry.get('req_id'),
        "cache_hit": telemetry.get('cache_hit', False),
        "stages": telemetry.get('stage_lat_ms', {}),
        "total_time": telemetry.get('stage_lat_ms', {}).get('total', 0)
    }

    # 检查是否调用了LLM
    stages = telemetry.get('stage_lat_ms', {})
    if 'llm' in stages:
        analysis["llm_called"] = True
        analysis["llm_time"] = stages['llm']
    else:
        analysis["llm_called"] = False

    return analysis

def test_t1_wechat_search_basic():
    """T1: 微信主界面点击搜索（无intent，无hints）"""
    print("\n" + "="*70)
    print("🧪 T1测试: 微信主界面点击搜索（无intent无hints）")
    print("="*70)

    test_images = load_test_images()
    if not test_images:
        return False

    wechat_data = test_images['wechat_main']

    payload = {
        "image": {"base64": wechat_data['base64'], "format": "png"},
        "capture": {"mode": "full", "screen_size": wechat_data['screen_size'], "dpr": 1.0},
        "context": {
            "goal": "点击搜索按钮"
        },
        "options": {
            "max_candidates": 24,
            "yolo": {"conf": 0.3, "iou": 0.45},
            "return_overlay": True
        },
        "idempotency_key": "t1-wechat-click-search"
    }

    result = make_request("http://127.0.0.1:8000/v1/pick", payload)
    if not result:
        return False

    analysis = analyze_response(result, "T1")

    print(f"📊 T1 分析结果:")
    print(f"   ✅ API调用: {'成功' if analysis['success'] else '失败'}")
    print(f"   ✅ 有决策: {'是' if analysis['has_decision'] else '否'}")
    if analysis['has_decision']:
        dec = analysis['decision']
        print(f"   📍 动作: {dec['action']}")
        print(f"   📍 置信度: {dec['confidence']:.1%}")
        print(f"   📍 点击点: {dec['point']}")
        print(f"   📍 推理: {dec['reason_preview']}")
    print(f"   ✅ 调用LLM: {'是' if analysis['llm_called'] else '否'}")
    if analysis['llm_called']:
        print(f"   ⏱️  LLM耗时: {analysis['llm_time']}ms")
    print(f"   ✅ 有锚点: {'是' if analysis['has_anchor'] else '否'}")

    if analysis['errors']:
        print(f"   ❌ 错误: {'; '.join(analysis['errors'])}")

    # 保存锚点用于T5测试
    if analysis['has_anchor']:
        anchor_data = result['data']['anchor_proposal']
        with open('t1_anchor.json', 'w') as f:
            json.dump(anchor_data, f, indent=2)
        print(f"   💾 锚点已保存: t1_anchor.json")

    return analysis['success'] and analysis['has_decision'] and not analysis['errors']

def test_t2_browser_search_with_hints():
    """T2: 浏览器页面点击搜索（提供中英文hints）"""
    print("\n" + "="*70)
    print("🧪 T2测试: 浏览器页面点击搜索（提供中英文hints）")
    print("="*70)

    test_images = load_test_images()
    if not test_images:
        return False

    browser_data = test_images['browser_search']

    payload = {
        "image": {"base64": browser_data['base64'], "format": "png"},
        "capture": {"mode": "full", "screen_size": browser_data['screen_size'], "dpr": 1.0},
        "context": {
            "goal": "点击页面上的搜索",
            "intent": "click",
            "vars": {"site": "xiaohongshu"},
            "dom_hints": {"text": ["搜索", "Search", "submit", "magnifier"]}
        },
        "options": {"max_candidates": 48, "return_overlay": True},
        "idempotency_key": "t2-xhs-click-search"
    }

    result = make_request("http://127.0.0.1:8000/v1/pick", payload)
    if not result:
        return False

    analysis = analyze_response(result, "T2")

    print(f"📊 T2 分析结果:")
    print(f"   ✅ API调用: {'成功' if analysis['success'] else '失败'}")
    print(f"   ✅ 有决策: {'是' if analysis['has_decision'] else '否'}")
    if analysis['has_decision']:
        dec = analysis['decision']
        print(f"   📍 动作: {dec['action']}")
        print(f"   📍 置信度: {dec['confidence']:.1%}")
        print(f"   📍 点击点: {dec['point']}")
        print(f"   📍 推理: {dec['reason_preview']}")
    print(f"   ✅ 调用LLM: {'是' if analysis['llm_called'] else '否'}")
    if analysis['llm_called']:
        print(f"   ⏱️  LLM耗时: {analysis['llm_time']}ms")
    print(f"   ✅ 有验证计划: {'是' if analysis['has_verification_plan'] else '否'}")

    if analysis['errors']:
        print(f"   ❌ 错误: {'; '.join(analysis['errors'])}")

    # 保存验证计划用于T7测试
    if analysis['has_verification_plan']:
        verification_plan = result['data']['verification_plan']
        with open('t2_verification.json', 'w') as f:
            json.dump(verification_plan, f, indent=2)
        print(f"   💾 验证计划已保存: t2_verification.json")

    return analysis['success'] and analysis['has_decision'] and not analysis['errors']

def test_t3_login_button():
    """T3: 登录页面点击登录按钮（中文goal）"""
    print("\n" + "="*70)
    print("🧪 T3测试: 登录页面点击登录按钮（中文goal）")
    print("="*70)

    test_images = load_test_images()
    if not test_images:
        return False

    login_data = test_images['login_page']

    payload = {
        "image": {"base64": login_data['base64'], "format": "png"},
        "capture": {"mode": "full", "screen_size": login_data['screen_size'], "dpr": 1.25},
        "context": {
            "goal": "点击登录按钮",
            "intent": "click",
            "vars": {"site": "login_page"},
            "dom_hints": {"text": ["登录", "Sign in", "submit"]}
        },
        "options": {"max_candidates": 32},
        "idempotency_key": "t3-login-click-button"
    }

    result = make_request("http://127.0.0.1:8000/v1/pick", payload)
    if not result:
        return False

    analysis = analyze_response(result, "T3")

    print(f"📊 T3 分析结果:")
    print(f"   ✅ API调用: {'成功' if analysis['success'] else '失败'}")
    print(f"   ✅ 有决策: {'是' if analysis['has_decision'] else '否'}")
    if analysis['has_decision']:
        dec = analysis['decision']
        print(f"   📍 动作: {dec['action']}")
        print(f"   📍 置信度: {dec['confidence']:.1%}")
        print(f"   📍 点击点: {dec['point']}")
        print(f"   📍 推理: {dec['reason_preview']}")

    # 检查DPR映射
    mapping_hint = analysis.get('mapping_hint', {})
    expected_dpr = mapping_hint.get('expects_dpr', 1.0)
    print(f"   📐 预期DPR: {expected_dpr} (请求DPR: 1.25)")

    if analysis['errors']:
        print(f"   ❌ 错误: {'; '.join(analysis['errors'])}")

    return analysis['success'] and analysis['has_decision'] and not analysis['errors']

def test_t4_username_input():
    """T4: 点击用户名输入框（intent=输入）"""
    print("\n" + "="*70)
    print("🧪 T4测试: 点击用户名输入框（intent=输入）")
    print("="*70)

    test_images = load_test_images()
    if not test_images:
        return False

    login_data = test_images['login_page']

    payload = {
        "image": {"base64": login_data['base64'], "format": "png"},
        "capture": {"mode": "full", "screen_size": login_data['screen_size'], "dpr": 1.25},
        "context": {
            "goal": "点击用户名输入框",
            "intent": "输入",
            "vars": {"site": "login_page"}
        },
        "options": {"max_candidates": 32},
        "idempotency_key": "t4-login-click-username"
    }

    result = make_request("http://127.0.0.1:8000/v1/pick", payload)
    if not result:
        return False

    analysis = analyze_response(result, "T4")

    print(f"📊 T4 分析结果:")
    print(f"   ✅ API调用: {'成功' if analysis['success'] else '失败'}")
    print(f"   ✅ 有决策: {'是' if analysis['has_decision'] else '否'}")
    if analysis['has_decision']:
        dec = analysis['decision']
        print(f"   📍 动作: {dec['action']}")
        print(f"   📍 置信度: {dec['confidence']:.1%}")
        print(f"   📍 点击点: {dec['point']}")
        print(f"   📍 推理: {dec['reason_preview']}")

        # 检查是否提到input/textbox
        reason = dec.get('reason_preview', '').lower()
        if any(word in reason for word in ['input', 'textbox', '输入', '文本框']):
            print(f"   ✅ 推理提到输入相关概念")
        else:
            print(f"   ⚠️  推理未明确提到输入框")

    if analysis['errors']:
        print(f"   ❌ 错误: {'; '.join(analysis['errors'])}")

    return analysis['success'] and analysis['has_decision'] and not analysis['errors']

def test_t5_anchor_reuse():
    """T5: 锚点复用验证（两次调用对比）"""
    print("\n" + "="*70)
    print("🧪 T5测试: 锚点复用验证（两次调用对比）")
    print("="*70)

    # 检查是否有保存的锚点
    try:
        with open('t1_anchor.json', 'r') as f:
            anchor_data = json.load(f)
        print(f"✅ 加载锚点: {anchor_data.get('id', 'unknown')}")
    except FileNotFoundError:
        print("❌ 未找到T1测试保存的锚点，请先运行T1测试")
        return False

    test_images = load_test_images()
    if not test_images:
        return False

    wechat_data = test_images['wechat_main']

    payload = {
        "image": {"base64": wechat_data['base64'], "format": "png"},
        "capture": {"mode": "full", "screen_size": wechat_data['screen_size'], "dpr": 1.0},
        "context": {"goal": "点击搜索按钮"},
        "anchors_known": [anchor_data],
        "options": {"max_candidates": 24},
        "idempotency_key": "t5-anchor-reuse"
    }

    result = make_request("http://127.0.0.1:8000/v1/pick", payload)
    if not result:
        return False

    analysis = analyze_response(result, "T5")

    print(f"📊 T5 分析结果:")
    print(f"   ✅ API调用: {'成功' if analysis['success'] else '失败'}")
    print(f"   ✅ 有决策: {'是' if analysis['has_decision'] else '否'}")
    if analysis['has_decision']:
        dec = analysis['decision']
        print(f"   📍 动作: {dec['action']}")
        print(f"   📍 置信度: {dec['confidence']:.1%}")
        print(f"   📍 点击点: {dec['point']}")
        print(f"   📍 推理: {dec['reason_preview']}")

        # 检查是否是锚点命中
        reason = dec.get('reason_preview', '').lower()
        if any(word in reason for word in ['anchor', 'hit', '锚点', '命中', '缓存']):
            print(f"   ✅ 检测到锚点命中")
        else:
            print(f"   ⚠️  未明确显示锚点命中")

    print(f"   📈 缓存命中: {'是' if analysis['telemetry']['cache_hit'] else '否'}")
    print(f"   ⏱️  调用LLM: {'是' if analysis['llm_called'] else '否'}")

    if analysis['llm_called']:
        print(f"   ⚠️  注意：锚点复用仍调用了LLM，可能锚点匹配失败")
    else:
        print(f"   ✅ 锚点复用成功，未调用LLM")

    if analysis['errors']:
        print(f"   ❌ 错误: {'; '.join(analysis['errors'])}")

    return analysis['success'] and analysis['has_decision'] and not analysis['errors']

def main():
    """运行所有测试"""
    print("🚀 开始端到端测试")
    print("测试YOLO+LLM决策服务完整链路")

    test_results = {}

    # 运行核心测试
    test_results["T1"] = test_t1_wechat_search_basic()
    test_results["T2"] = test_t2_browser_search_with_hints()
    test_results["T3"] = test_t3_login_button()
    test_results["T4"] = test_t4_username_input()
    test_results["T5"] = test_t5_anchor_reuse()

    # 总结报告
    print("\n" + "="*70)
    print("🏁 测试总结")
    print("="*70)

    passed = sum(test_results.values())
    total = len(test_results)

    for test_name, success in test_results.items():
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{test_name}: {status}")

    print(f"\n📊 总体结果: {passed}/{total} ({passed/total:.1%})")

    if passed == total:
        print("🎉 所有核心测试通过! YOLO+LLM服务ready for client!")
    elif passed >= 3:
        print("⚠️  大部分测试通过，服务基本可用，有小问题需修复")
    else:
        print("❌ 多个测试失败，需要重大修复")

if __name__ == "__main__":
    main()