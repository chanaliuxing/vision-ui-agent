#!/bin/bash

# YOLO+LLM 系统服务状态检查脚本
# 检查所有服务的运行状态和健康情况

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔍 YOLO+LLM 系统服务状态检查${NC}"
echo -e "${BLUE}======================================${NC}"

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 检查端口占用
check_port_usage() {
    echo -e "${YELLOW}📊 检查端口占用情况...${NC}"

    ports=(
        "8000|YOLO Detection API"
        "8001|OCR API"
        "8002|Workflow Generation API"
        "8003|Recall/Memory API"
        "8787|GetContent Backend"
        "8788|Orchestrator"
        "8080|Traefik Dashboard"
        "4566|LocalStack (AWS)"
    )

    for port_info in "${ports[@]}"; do
        port="${port_info%|*}"
        name="${port_info#*|}"

        if lsof -i:$port >/dev/null 2>&1; then
            pid=$(lsof -ti:$port)
            echo -e "${GREEN}✅ $name (端口 $port) - PID: $pid${NC}"
        else
            echo -e "${RED}❌ $name (端口 $port) - 未运行${NC}"
        fi
    done
    echo ""
}

# 检查 API 健康状态
check_api_health() {
    echo -e "${YELLOW}🏥 检查 API 健康状态...${NC}"

    services=(
        "YOLO API|http://127.0.0.1:8000/health"
        "OCR API|http://127.0.0.1:8001/health"
        "Workflow API|http://127.0.0.1:8002/health"
        "Recall API|http://127.0.0.1:8003/health"
        "GetContent Backend|http://127.0.0.1:8787/health"
        "Orchestrator|http://127.0.0.1:8788/health"
    )

    for service in "${services[@]}"; do
        name="${service%|*}"
        url="${service#*|}"

        response=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")

        if [ "$response" = "200" ]; then
            echo -e "${GREEN}✅ $name - 健康${NC}"
        else
            echo -e "${RED}❌ $name - 不健康 (HTTP: $response)${NC}"
        fi
    done
    echo ""
}

# 检查 Docker 服务
check_docker_services() {
    echo -e "${YELLOW}🐳 检查 Docker 服务...${NC}"

    if ! docker info >/dev/null 2>&1; then
        echo -e "${RED}❌ Docker 未运行${NC}"
        return
    fi

    services=("traefik" "localstack")

    for service in "${services[@]}"; do
        status=$(docker compose ps --services --filter "status=running" | grep "^$service$" || echo "")

        if [ -n "$status" ]; then
            echo -e "${GREEN}✅ $service - 运行中${NC}"
        else
            echo -e "${RED}❌ $service - 未运行${NC}"
        fi
    done
    echo ""
}

# 检查进程状态
check_process_status() {
    echo -e "${YELLOW}⚙️  检查进程状态...${NC}"

    services=("yolo_api" "ocr_api" "workflow_api" "recall_api" "getcontent_backend" "orchestrator")

    for service in "${services[@]}"; do
        if [ -f "/tmp/${service}.pid" ]; then
            pid=$(cat "/tmp/${service}.pid")
            if kill -0 "$pid" 2>/dev/null; then
                # 获取进程信息
                cmd=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
                echo -e "${GREEN}✅ $service - PID: $pid ($cmd)${NC}"
            else
                echo -e "${RED}❌ $service - PID 文件存在但进程不存在 ($pid)${NC}"
            fi
        else
            echo -e "${YELLOW}⚠️  $service - 无 PID 文件${NC}"
        fi
    done
    echo ""
}

# 检查扩展连接
check_extension_connection() {
    echo -e "${YELLOW}🌐 检查 Chrome 扩展连接...${NC}"

    # 测试登录
    response=$(curl -s -X POST http://localhost:8787/auth/login \
        -H "Content-Type: application/json" \
        -d '{"username":"test","password":"test"}' 2>/dev/null || echo "")

    if echo "$response" | grep -q "account_id"; then
        account_id=$(echo "$response" | grep -o '"account_id":"[^"]*"' | cut -d'"' -f4)
        echo -e "${GREEN}✅ 扩展后端连接正常 - 账户: $account_id${NC}"
    else
        echo -e "${RED}❌ 扩展后端连接失败${NC}"
    fi
    echo ""
}

# 检查日志文件
check_log_files() {
    echo -e "${YELLOW}📄 检查日志文件...${NC}"

    logs=("yolo_api" "ocr_api" "workflow_api" "recall_api" "getcontent_backend" "orchestrator")

    for log in "${logs[@]}"; do
        logfile="/tmp/${log}.log"
        if [ -f "$logfile" ]; then
            size=$(stat -f%z "$logfile" 2>/dev/null || stat -c%s "$logfile" 2>/dev/null)
            lines=$(wc -l < "$logfile")
            echo -e "${GREEN}✅ $log.log - $size 字节, $lines 行${NC}"
        else
            echo -e "${YELLOW}⚠️  $log.log - 文件不存在${NC}"
        fi
    done
    echo ""
}

# 系统资源使用情况
check_system_resources() {
    echo -e "${YELLOW}💻 系统资源使用情况...${NC}"

    # CPU 使用率
    if command -v top >/dev/null; then
        cpu_usage=$(top -l 1 -s 0 | grep "CPU usage" | awk '{print $3}' || echo "N/A")
        echo -e "${BLUE}CPU 使用率: $cpu_usage${NC}"
    fi

    # 内存使用
    if command -v vm_stat >/dev/null; then
        # macOS
        free_pages=$(vm_stat | grep "Pages free" | awk '{print $3}' | sed 's/\.//')
        total_pages=$(vm_stat | grep -E "Pages (free|active|inactive|speculative|wired)" | awk '{sum += $3} END {print sum}')
        if [ -n "$free_pages" ] && [ -n "$total_pages" ]; then
            used_percent=$(echo "scale=1; (($total_pages - $free_pages) * 100) / $total_pages" | bc 2>/dev/null || echo "N/A")
            echo -e "${BLUE}内存使用率: ${used_percent}%${NC}"
        fi
    elif command -v free >/dev/null; then
        # Linux
        mem_info=$(free | grep Mem)
        total=$(echo $mem_info | awk '{print $2}')
        used=$(echo $mem_info | awk '{print $3}')
        used_percent=$(echo "scale=1; ($used * 100) / $total" | bc)
        echo -e "${BLUE}内存使用率: ${used_percent}%${NC}"
    fi

    echo ""
}

# 显示日志尾部（可选）
show_recent_logs() {
    if [ "$1" = "--logs" ]; then
        echo -e "${YELLOW}📋 最新日志信息...${NC}"

        logs=("yolo_api" "ocr_api" "workflow_api" "recall_api" "getcontent_backend" "orchestrator")

        for log in "${logs[@]}"; do
            logfile="/tmp/${log}.log"
            if [ -f "$logfile" ]; then
                echo -e "${BLUE}--- $log.log (最新 5 行) ---${NC}"
                tail -5 "$logfile" | sed 's/^/  /'
                echo ""
            fi
        done
    fi
}

# 显示操作建议
show_recommendations() {
    echo -e "${BLUE}🔧 操作建议：${NC}"
    echo "• 启动所有服务: ./scripts/start_all_services.sh"
    echo "• 停止所有服务: ./scripts/stop_all_services.sh"
    echo "• 查看日志:     $0 --logs"
    echo "• 重新检查:     $0"
    echo ""
    echo -e "${YELLOW}Chrome 扩展：${NC}"
    echo "• 扩展目录: $PROJECT_ROOT/getcontent/extension/"
    echo "• 登录账户: test / test"
    echo ""
}

# 主执行流程
main() {
    check_port_usage
    check_api_health
    check_docker_services
    check_process_status
    check_extension_connection
    check_log_files
    check_system_resources
    show_recent_logs "$1"
    show_recommendations

    echo -e "${GREEN}🎊 状态检查完成！${NC}"
}

# 执行主函数
main "$@"