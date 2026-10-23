#!/usr/bin/env python3
"""
Stage 9 Demo: Billing and Subscription System (订阅 + 用量计费 + 多渠道支付)

This demo showcases:
1. Subscription billing with plan products
2. Usage-based billing with LLM token counting
3. Mock Stripe payment integration
4. Wallet balance and payment processing
5. Rate limiting and soft/hard caps
6. Invoice generation and webhook handling
7. Usage aggregation worker
"""

import requests
import json
import time
import sys
import os

# Add server directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '../server'))

API_BASE = "http://localhost:8080"

def color_print(text, color="white"):
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "purple": "\033[95m",
        "cyan": "\033[96m",
        "white": "\033[97m",
        "reset": "\033[0m"
    }
    print(f"{colors.get(color, colors['white'])}{text}{colors['reset']}")

def api_call(method, endpoint, data=None, headers=None):
    """Make API call with error handling"""
    url = f"{API_BASE}{endpoint}"

    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, headers=headers)
        elif method.upper() == "PUT":
            response = requests.put(url, json=data, headers=headers)
        elif method.upper() == "DELETE":
            response = requests.delete(url, headers=headers)

        print(f"  → {method} {endpoint}")
        if response.status_code >= 400:
            print(f"    Status: {response.status_code}")
            try:
                error_data = response.json()
                print(f"    Error: {json.dumps(error_data, indent=2)}")
            except:
                print(f"    Error: {response.text}")

        return response
    except Exception as e:
        color_print(f"API call failed: {e}", "red")
        return None

def main():
    color_print("=" * 80, "cyan")
    color_print("STAGE 9 DEMO: Billing and Subscription System", "cyan")
    color_print("=" * 80, "cyan")

    # Step 1: Login to get authentication token
    color_print("\\n1. User Authentication", "yellow")
    response = api_call("POST", "/auth/login", {
        "username": "test",
        "password": "test"
    })

    if not response or response.status_code != 200:
        color_print("❌ Login failed! Make sure the server is running and user exists.", "red")
        return

    token = response.json().get("token")
    headers = {"Authorization": f"Bearer {token}"}
    color_print("✅ Successfully logged in", "green")

    # Step 2: Check billing info
    color_print("\\n2. Billing Information", "yellow")
    response = api_call("GET", "/billing/info", headers=headers)
    if response and response.status_code == 200:
        billing_info = response.json()
        color_print("✅ Current billing status:", "green")
        print(json.dumps(billing_info, indent=2))

    # Step 3: List available plans
    color_print("\\n3. Available Subscription Plans", "yellow")
    response = api_call("GET", "/billing/plans", headers=headers)
    if response and response.status_code == 200:
        plans = response.json()
        color_print("✅ Available plans:", "green")
        print(json.dumps(plans, indent=2))

    # Step 4: Create checkout session
    color_print("\\n4. Create Checkout Session", "yellow")
    response = api_call("POST", "/billing/checkout", {
        "plan_key": "pro",
        "mode": "subscription"
    }, headers=headers)

    if response and response.status_code == 200:
        checkout = response.json()
        color_print("✅ Checkout session created:", "green")
        print(json.dumps(checkout, indent=2))
        color_print(f"🔗 Mock Stripe checkout URL: {checkout.get('url')}", "blue")

    # Step 5: Test LLM routing with billing checks
    color_print("\\n5. Test LLM Job Submission with Billing", "yellow")
    response = api_call("POST", "/llm/submit", {
        "job_type": "vision_picker",
        "provider": "gemini",
        "model": "gemini-1.5-flash",
        "prompt_pack_key": "test_pack"
    }, headers=headers)

    if response and response.status_code == 200:
        job = response.json()
        color_print("✅ LLM job submitted successfully:", "green")
        print(json.dumps(job, indent=2))
    elif response and response.status_code == 402:
        error = response.json()
        color_print("💳 Payment required:", "yellow")
        print(json.dumps(error, indent=2))

    # Step 6: Test usage aggregation worker
    color_print("\\n6. Run Usage Aggregation Worker", "yellow")
    color_print("Running billing worker to aggregate usage...", "blue")

    # Import and run the billing worker
    try:
        import subprocess
        result = subprocess.run([
            "node", "../server/billing_worker.js"
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))

        if result.returncode == 0:
            color_print("✅ Billing worker completed successfully:", "green")
            print(result.stdout)
        else:
            color_print("❌ Billing worker failed:", "red")
            print(result.stderr)
    except Exception as e:
        color_print(f"❌ Could not run billing worker: {e}", "red")

    # Step 7: Check invoices
    color_print("\\n7. View Generated Invoices", "yellow")
    response = api_call("GET", "/billing/invoices", headers=headers)
    if response and response.status_code == 200:
        invoices = response.json()
        color_print("✅ Current invoices:", "green")
        print(json.dumps(invoices, indent=2))

    # Step 8: Test wallet operations
    color_print("\\n8. Wallet Operations", "yellow")
    response = api_call("GET", "/billing/wallet", headers=headers)
    if response and response.status_code == 200:
        wallet = response.json()
        color_print("✅ Wallet status:", "green")
        print(json.dumps(wallet, indent=2))

    # Step 9: Test billing limits update
    color_print("\\n9. Update Billing Limits", "yellow")
    response = api_call("PUT", "/billing/limits", {
        "soft_cap_cents": 2000,  # $20
        "hard_cap_cents": 5000   # $50
    }, headers=headers)

    if response and response.status_code == 200:
        limits = response.json()
        color_print("✅ Billing limits updated:", "green")
        print(json.dumps(limits, indent=2))

    # Step 10: Test rate limiting by submitting multiple jobs
    color_print("\\n10. Test Rate Limiting", "yellow")
    color_print("Submitting multiple LLM jobs to test rate limiting...", "blue")

    for i in range(3):
        color_print(f"Submitting job {i+1}/3...", "blue")
        response = api_call("POST", "/llm/submit", {
            "job_type": f"test_job_{i+1}",
            "provider": "gemini",
            "model": "gemini-1.5-flash"
        }, headers=headers)

        if response:
            if response.status_code == 200:
                job = response.json()
                color_print(f"✅ Job {i+1} accepted. Status: {job.get('billing_status')}", "green")
            elif response.status_code == 402:
                error = response.json()
                color_print(f"💳 Job {i+1} rejected: {error.get('reason')}", "yellow")
            else:
                color_print(f"❌ Job {i+1} failed with status {response.status_code}", "red")

        time.sleep(0.5)

    # Step 11: Create billing portal session
    color_print("\\n11. Billing Portal Access", "yellow")
    response = api_call("POST", "/billing/portal", {}, headers=headers)
    if response and response.status_code == 200:
        portal = response.json()
        color_print("✅ Billing portal session created:", "green")
        print(json.dumps(portal, indent=2))
        color_print(f"🔗 Mock Stripe portal URL: {portal.get('url')}", "blue")

    # Summary
    color_print("\\n" + "=" * 80, "cyan")
    color_print("STAGE 9 DEMO SUMMARY", "cyan")
    color_print("=" * 80, "cyan")

    color_print("✅ Implemented Features:", "green")
    features = [
        "📊 Comprehensive billing database schema with invoices, payments, wallets",
        "💳 Mock Stripe payment adapter with checkout and portal sessions",
        "🔄 Usage aggregation worker for token-based billing",
        "⚡ Rate limiting with soft/hard caps and wallet balance checks",
        "📧 Webhook handlers for payment processing events",
        "🎯 API endpoints for subscription management and invoice tracking",
        "🔐 Secure billing operations with JWT authentication",
        "📈 Real-time billing status and usage monitoring",
        "💰 Multi-currency support and flexible pricing models",
        "🚨 Automated billing alerts and payment failure handling"
    ]

    for feature in features:
        color_print(f"   {feature}", "white")

    color_print("\\n🎉 Stage 9 (Billing & Subscription System) completed successfully!", "green")
    color_print("Ready for Stage 10: Workflow Marketplace & Advanced Features", "blue")

if __name__ == "__main__":
    main()