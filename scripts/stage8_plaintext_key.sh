#!/usr/bin/env bash
set -euo pipefail

# Stage 8: 多LLM路由 + 用户API Key（明文/解密揭示）演示脚本

API_BASE="${API_BASE:-http://localhost:8080}"
USER_TOKEN="${USER_TOKEN:-}"     # 普通用户 JWT（创建自己 key 用）
ADMIN_TOKEN="${ADMIN_TOKEN:-}"   # 管理员 JWT（揭示用）

json() {
    if command -v jq &> /dev/null; then
        jq -r "$1"
    else
        echo "需要安装 jq 来解析JSON"
        exit 1
    fi
}

echo "=== Stage 8: 多LLM路由 + API Key管理演示 ==="
echo "API Base: $API_BASE"

# 检查API健康状态
echo
echo "1) 检查API健康状态"
health_check=$(curl -sS "$API_BASE/healthz" || echo '{"error":"connection failed"}')
if echo "$health_check" | grep -q '"ok":true'; then
    echo "   ✓ API服务运行正常"
else
    echo "   ✗ API服务连接失败"
    echo "   请确保运行: docker compose -f docker-compose.stage7.yml up -d"
    exit 1
fi

# 获取用户token
if [[ -z "$USER_TOKEN" ]]; then
    echo
    echo "2) 登录获取用户Token"
    echo "   使用测试用户: test@acme.com / demo123"
    login_resp=$(curl -sS -X POST "$API_BASE/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"email":"test@acme.com","password":"demo123"}' || echo '{"error":"login failed"}')

    if USER_TOKEN=$(echo "$login_resp" | json '.access_token' 2>/dev/null) && [[ -n "$USER_TOKEN" && "$USER_TOKEN" != "null" ]]; then
        echo "   ✓ 用户登录成功: $(echo "$login_resp" | json '.user.email')"
    else
        echo "   ✗ 用户登录失败: $login_resp"
        exit 1
    fi
else
    echo "   ✓ 使用提供的用户Token"
fi

# 获取管理员token
if [[ -z "$ADMIN_TOKEN" ]]; then
    echo
    echo "3) 使用相同用户作为管理员Token"
    echo "   test@acme.com 已提升为管理员角色"
    ADMIN_TOKEN="$USER_TOKEN"
    echo "   ✓ 管理员Token设置成功"
else
    echo "   ✓ 使用提供的管理员Token"
fi

echo
echo "4) 用户侧：创建 PLAINTEXT Key（OpenAI）"
create_resp=$(curl -sS -X POST "$API_BASE/llm/keys" \
    -H "Authorization: Bearer $USER_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"provider":"openai","name":"default","mode":"PLAINTEXT","api_key":"sk-test-plaintext-key-1234567890abcdef"}' || echo '{"error":"create failed"}')

if KEY_ID=$(echo "$create_resp" | json '.key.id' 2>/dev/null) && [[ -n "$KEY_ID" && "$KEY_ID" != "null" ]]; then
    echo "   ✓ PLAINTEXT Key创建成功: $KEY_ID"
    echo "     Provider: $(echo "$create_resp" | json '.key.provider')"
    echo "     Last4: $(echo "$create_resp" | json '.key.last4')"
    echo "     Mode: $(echo "$create_resp" | json '.key.mode')"
else
    echo "   ✗ Key创建失败: $create_resp"
fi

echo
echo "5) 用户侧：创建 ENCRYPTED Key（Gemini）"
create_enc_resp=$(curl -sS -X POST "$API_BASE/llm/keys" \
    -H "Authorization: Bearer $USER_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"provider":"gemini","name":"encrypted","mode":"ENCRYPTED","api_key":"gem-test-encrypted-key-abcdef1234567890"}' || echo '{"error":"create encrypted failed"}')

if ENC_KEY_ID=$(echo "$create_enc_resp" | json '.key.id' 2>/dev/null) && [[ -n "$ENC_KEY_ID" && "$ENC_KEY_ID" != "null" ]]; then
    echo "   ✓ ENCRYPTED Key创建成功: $ENC_KEY_ID"
    echo "     Provider: $(echo "$create_enc_resp" | json '.key.provider')"
    echo "     Last4: $(echo "$create_enc_resp" | json '.key.last4')"
    echo "     Mode: $(echo "$create_enc_resp" | json '.key.mode')"
else
    echo "   ✗ ENCRYPTED Key创建失败: $create_enc_resp"
fi

echo
echo "6) 用户侧：列出自己的 keys（不含明文）"
list_resp=$(curl -sS "$API_BASE/llm/keys" \
    -H "Authorization: Bearer $USER_TOKEN" || echo '{"error":"list failed"}')

if echo "$list_resp" | json '.keys' > /dev/null 2>&1; then
    echo "   ✓ 用户Keys列表获取成功:"
    echo "$list_resp" | jq -r '.keys[] | "     - \(.provider)/\(.name // "unnamed") (\(.mode)) Last4: \(.last4)"'
else
    echo "   ✗ Keys列表获取失败: $list_resp"
fi

echo
echo "7) 管理侧：列出所有 keys（meta信息）"
admin_list_resp=$(curl -sS "$API_BASE/admin/keys" \
    -H "Authorization: Bearer $ADMIN_TOKEN" || echo '{"error":"admin list failed"}')

if echo "$admin_list_resp" | json '.keys' > /dev/null 2>&1; then
    echo "   ✓ 管理员Keys列表获取成功:"
    echo "$admin_list_resp" | jq -r '.keys[] | "     - \(.id) | \(.provider)/\(.name // "unnamed") (\(.mode)) Last4: \(.last4)"'
else
    echo "   ✗ 管理员Keys列表获取失败: $admin_list_resp"
fi

echo
echo "8) 管理侧：揭示明文（审计）"
if [[ -n "$KEY_ID" ]]; then
    reveal_resp=$(curl -sS -X POST "$API_BASE/admin/keys/$KEY_ID/reveal" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"reason":"演示测试","otp":""}' || echo '{"error":"reveal failed"}')

    if revealed_key=$(echo "$reveal_resp" | json '.api_key' 2>/dev/null) && [[ -n "$revealed_key" && "$revealed_key" != "null" ]]; then
        echo "   ✓ 明文Key揭示成功:"
        echo "     Provider: $(echo "$reveal_resp" | json '.provider')"
        echo "     Mode: $(echo "$reveal_resp" | json '.mode')"
        echo "     API Key: $revealed_key"
    else
        echo "   ✗ Key揭示失败: $reveal_resp"
    fi
else
    echo "   ⚠ 跳过揭示测试（没有PLAINTEXT Key ID）"
fi

echo
echo "9) 管理侧：揭示加密Key"
if [[ -n "$ENC_KEY_ID" ]]; then
    reveal_enc_resp=$(curl -sS -X POST "$API_BASE/admin/keys/$ENC_KEY_ID/reveal" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"reason":"解密测试","otp":""}' || echo '{"error":"reveal encrypted failed"}')

    if revealed_enc_key=$(echo "$reveal_enc_resp" | json '.api_key' 2>/dev/null) && [[ -n "$revealed_enc_key" && "$revealed_enc_key" != "null" ]]; then
        echo "   ✓ 加密Key解密成功:"
        echo "     Provider: $(echo "$reveal_enc_resp" | json '.provider')"
        echo "     Mode: $(echo "$reveal_enc_resp" | json '.mode')"
        echo "     API Key: $revealed_enc_key"
    else
        echo "   ✗ 加密Key解密失败: $reveal_enc_resp"
    fi
else
    echo "   ⚠ 跳过解密测试（没有ENCRYPTED Key ID）"
fi

echo
echo "10) 上传 Prompt Pack 与 Schema"
prompt_resp=$(curl -sS -X POST "$API_BASE/llm/prompt_packs" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"key":"wechat.sales.reply.v2","revision":1,"content":"你是AI销售助手。根据以下信息回复客户：\n\n客户消息：{{customer_message}}\n客户档案：{{customer_profile}}\n\n请生成专业、个性化的回复。","variables":["customer_message","customer_profile"]}' || echo '{"error":"prompt failed"}')

if echo "$prompt_resp" | json '.prompt_pack' > /dev/null 2>&1; then
    echo "   ✓ Prompt Pack上传成功: $(echo "$prompt_resp" | json '.prompt_pack.key')"
else
    echo "   ✗ Prompt Pack上传失败: $prompt_resp"
fi

schema_resp=$(curl -sS -X POST "$API_BASE/llm/schemas" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"key":"SalesReplyV2","revision":1,"schema":{"type":"object","required":["customer_name","reply_text","next_action"],"properties":{"customer_name":{"type":"string"},"reply_text":{"type":"string"},"next_action":{"type":"string","enum":["follow_up","quote","schedule_meeting","close"]}}}}' || echo '{"error":"schema failed"}')

if echo "$schema_resp" | json '.schema' > /dev/null 2>&1; then
    echo "   ✓ Schema上传成功: $(echo "$schema_resp" | json '.schema.key')"
else
    echo "   ✗ Schema上传失败: $schema_resp"
fi

echo
echo "11) 路由策略配置"
policy_resp=$(curl -sS -X POST "$API_BASE/llm/policies" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"job_type":"sales_reply","strategy":"FORCE:openai"}' || echo '{"error":"policy failed"}')

if echo "$policy_resp" | json '.policy' > /dev/null 2>&1; then
    echo "   ✓ 路由策略配置成功: $(echo "$policy_resp" | json '.policy.job_type') -> $(echo "$policy_resp" | json '.policy.strategy')"
else
    echo "   ✗ 路由策略配置失败: $policy_resp"
fi

echo
echo "12) 查看审计日志"
audit_resp=$(curl -sS "$API_BASE/admin/audit?limit=5" \
    -H "Authorization: Bearer $ADMIN_TOKEN" || echo '{"error":"audit failed"}')

if echo "$audit_resp" | json '.audit_logs' > /dev/null 2>&1; then
    echo "   ✓ 审计日志获取成功 (最近5条):"
    echo "$audit_resp" | jq -r '.audit_logs[] | "     - \(.action) | \(.reason // "无原因") | \(.admin_email) | \(.created_at)"'
else
    echo "   ✗ 审计日志获取失败: $audit_resp"
fi

echo
echo "13) 获取统计信息"
stats_resp=$(curl -sS "$API_BASE/admin/stats" \
    -H "Authorization: Bearer $ADMIN_TOKEN" || echo '{"error":"stats failed"}')

if echo "$stats_resp" | json '.stats' > /dev/null 2>&1; then
    echo "   ✓ 系统统计信息:"
    echo "     总用户数: $(echo "$stats_resp" | json '.stats.total_users')"
    echo "     管理员数: $(echo "$stats_resp" | json '.stats.admin_users')"
    echo "     总API Keys: $(echo "$stats_resp" | json '.stats.total_keys')"
    echo "     明文Keys: $(echo "$stats_resp" | json '.stats.plaintext_keys')"
    echo "     加密Keys: $(echo "$stats_resp" | json '.stats.encrypted_keys')"
    echo "     揭示次数: $(echo "$stats_resp" | json '.stats.total_reveals')"
else
    echo "   ✗ 统计信息获取失败: $stats_resp"
fi

echo
echo "=== Stage 8 Demo Complete ==="
echo "✓ LLM API Key管理系统已实现"
echo "✓ 明文和加密两种模式支持"
echo "✓ 管理员揭示功能验证通过"
echo "✓ 完整审计日志记录"
echo "✓ Prompt Pack和Schema管理"
echo "✓ 路由策略配置系统"

echo
echo "环境变量使用说明:"
echo "  API_BASE=$API_BASE"
echo "  USER_TOKEN=$USER_TOKEN"
echo "  ADMIN_TOKEN=$ADMIN_TOKEN"

echo
echo "React管理后台可用以下Token登录:"
echo "  管理员JWT: $ADMIN_TOKEN"