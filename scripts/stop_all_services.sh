#!/bin/bash

# YOLO+LLM 系统一键停止脚本
# 停止所有运行中的服务

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🛑 YOLO+LLM 系统一键停止脚本${NC}"
echo -e "${BLUE}======================================${NC}"

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 停止 API 服务进程
stop_api_services() {
    echo -e "${YELLOW}🔧 停止核心 API 服务...${NC}"

    services=("yolo_api" "ocr_api" "workflow_api" "recall_api")

    for service in "${services[@]}"; do
        if [ -f "/tmp/${service}.pid" ]; then
            pid=$(cat "/tmp/${service}.pid")
            if kill -0 "$pid" 2>/dev/null; then
                echo -e "${BLUE}停止 $service (PID: $pid)...${NC}"
                kill "$pid"
                rm -f "/tmp/${service}.pid"
            else
                echo -e "${YELLOW}$service 进程不存在 (PID: $pid)${NC}"
                rm -f "/tmp/${service}.pid"
            fi
        else
            echo -e "${YELLOW}未找到 $service PID 文件${NC}"
        fi
    done

    echo -e "${GREEN}✅ 核心 API 服务停止完成${NC}"
}

# 停止 Chrome 扩展后端和 Orchestrator
stop_extension_backend() {
    echo -e "${YELLOW}🌐 停止 Chrome 扩展后端和 Orchestrator...${NC}"

    # 停止 GetContent 后端 (8787)
    if [ -f "/tmp/getcontent_backend.pid" ]; then
        pid=$(cat "/tmp/getcontent_backend.pid")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${BLUE}停止 GetContent 后端 (PID: $pid)...${NC}"
            kill "$pid"
            rm -f "/tmp/getcontent_backend.pid"
        else
            echo -e "${YELLOW}GetContent 后端进程不存在 (PID: $pid)${NC}"
            rm -f "/tmp/getcontent_backend.pid"
        fi
    else
        echo -e "${YELLOW}未找到 GetContent 后端 PID 文件${NC}"
    fi

    # 停止 Orchestrator (8788)
    if [ -f "/tmp/orchestrator.pid" ]; then
        pid=$(cat "/tmp/orchestrator.pid")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${BLUE}停止 Orchestrator (PID: $pid)...${NC}"
            kill "$pid"
            rm -f "/tmp/orchestrator.pid"
        else
            echo -e "${YELLOW}Orchestrator 进程不存在 (PID: $pid)${NC}"
            rm -f "/tmp/orchestrator.pid"
        fi
    else
        echo -e "${YELLOW}未找到 Orchestrator PID 文件${NC}"
    fi

    echo -e "${GREEN}✅ Chrome 扩展后端和 Orchestrator 停止完成${NC}"
}

# 停止基础设施服务
stop_infrastructure() {
    echo -e "${YELLOW}🏗️  停止基础设施服务...${NC}"

    # 停止 Docker 服务
    docker compose --profile gateway --profile localstack down

    echo -e "${GREEN}✅ 基础设施服务停止完成${NC}"
}

# 强制清理端口（备用方案）
force_cleanup_ports() {
    echo -e "${YELLOW}🧹 强制清理端口占用...${NC}"

    ports=(8000 8001 8002 8003 8787 8788)

    for port in "${ports[@]}"; do
        pids=$(lsof -ti:$port 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo -e "${BLUE}强制停止端口 $port 上的进程: $pids${NC}"
            echo "$pids" | xargs kill -9 2>/dev/null || true
        fi
    done

    echo -e "${GREEN}✅ 端口清理完成${NC}"
}

# 清理临时文件
cleanup_temp_files() {
    echo -e "${YELLOW}🗑️  清理临时文件...${NC}"

    # 清理 PID 文件
    rm -f /tmp/*_api.pid
    rm -f /tmp/getcontent_backend.pid
    rm -f /tmp/orchestrator.pid

    # 清理日志文件（可选）
    if [ "$1" = "--clean-logs" ]; then
        echo -e "${BLUE}清理日志文件...${NC}"
        rm -f /tmp/*_api.log
        rm -f /tmp/getcontent_backend.log
        rm -f /tmp/orchestrator.log
    fi

    echo -e "${GREEN}✅ 临时文件清理完成${NC}"
}

# 主执行流程
main() {
    echo -e "${BLUE}开始停止所有服务...${NC}"

    stop_api_services
    stop_extension_backend
    stop_infrastructure
    force_cleanup_ports
    cleanup_temp_files "$1"

    echo -e "${GREEN}🎊 所有服务已停止！${NC}"
    echo ""
    echo -e "${YELLOW}提示：${NC}"
    echo "• 如需清理日志文件，使用: $0 --clean-logs"
    echo "• 如需重新启动，使用: ./scripts/start_all_services.sh"
}

# 执行主函数
main "$@"