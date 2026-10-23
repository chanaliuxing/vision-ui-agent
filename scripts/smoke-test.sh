#!/bin/bash
# scripts/smoke-test.sh

set -e

BASE_URL="http://localhost"
TIMEOUT=30

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 测试API端点
test_endpoint() {
    local endpoint=$1
    local description=$2

    log_info "Testing $description..."

    if curl -f -s -m $TIMEOUT "$BASE_URL$endpoint" > /dev/null; then
        log_info "✅ $description - OK"
        return 0
    else
        log_error "❌ $description - FAILED"
        return 1
    fi
}

# 等待服务启动
log_info "🚀 Starting smoke tests..."
sleep 5

# 核心测试用例
TESTS=(
    "/api/v1/vision/yolo/health:YOLO API"
    "/api/v1/vision/ocr/health:OCR API"
    "/api/v1/workflow/health:Workflow API"
    "/api/v1/recall/health:Recall API"
    "/api/v1/vision/analysis/health:Vision Analysis API"
    "/api/v1/ml/dpo/health:DPO Service"
    "/api/v1/ml/models/health:Model Manager"
    "/api/v1/ml/experiments/health:A/B Testing"
)

failed=0
total=${#TESTS[@]}

for test in "${TESTS[@]}"; do
    IFS=':' read -r endpoint description <<< "$test"
    if ! test_endpoint "$endpoint" "$description"; then
        ((failed++))
    fi
done

# 测试Traefik仪表盘
if curl -f -s -m $TIMEOUT "http://localhost:8080/api/overview" > /dev/null; then
    log_info "✅ Traefik Dashboard - OK"
else
    log_warn "⚠️ Traefik Dashboard - Not accessible"
fi

# 结果汇总
echo ""
log_info "📊 Test Results:"
log_info "Total tests: $total"
log_info "Passed: $((total - failed))"
if [ $failed -gt 0 ]; then
    log_error "Failed: $failed"
    exit 1
else
    log_info "Failed: 0"
    log_info "🎉 All tests passed!"
fi