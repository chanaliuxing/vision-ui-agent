#!/bin/bash

# YOLO+LLM 系统一键启动脚本
# 启动所有核心服务：基础设施、API服务、Chrome扩展后端

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}🚀 YOLO+LLM 系统一键启动脚本${NC}"
echo -e "${BLUE}======================================${NC}"

# 检查虚拟环境
check_venv() {
    if [ ! -d "myenv" ]; then
        echo -e "${RED}❌ 未找到 myenv 虚拟环境${NC}"
        echo -e "${YELLOW}正在创建虚拟环境...${NC}"
        python -m venv myenv
        echo -e "${GREEN}✅ 虚拟环境创建完成${NC}"
    fi
}

# 检查 Docker
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        echo -e "${RED}❌ Docker 未运行，请先启动 Docker Desktop${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Docker 运行正常${NC}"
}

# 检查依赖
check_dependencies() {
    echo -e "${YELLOW}📦 检查依赖...${NC}"

    # 激活虚拟环境
    source myenv/bin/activate

    # 检查关键 Python 包
    if ! python -c "import uvicorn, fastapi" 2>/dev/null; then
        echo -e "${YELLOW}正在安装 Python 依赖...${NC}"
        pip install -r requirements.txt
    fi

    # 检查 Node.js 依赖
    if [ ! -d "getcontent/backend/node_modules" ]; then
        echo -e "${YELLOW}正在安装 Node.js 依赖...${NC}"
        cd getcontent/backend && npm install && cd "$PROJECT_ROOT"
    fi

    echo -e "${GREEN}✅ 依赖检查完成${NC}"
}

# 启动基础设施服务
start_infrastructure() {
    echo -e "${YELLOW}🏗️  启动基础设施服务...${NC}"

    # 启动 Docker 服务
    docker compose --profile gateway --profile localstack up -d

    # 等待服务启动
    echo -e "${YELLOW}等待基础设施服务启动...${NC}"
    wait_localstack

    # 初始化 AWS 服务
    source myenv/bin/activate
    if python scripts/bootstrap_infrastructure.py; then
        echo -e "${GREEN}✅ 基础设施服务启动完成${NC}"
    else
        echo -e "${RED}⚠️  基础设施引导（bootstrap_infrastructure.py）失败，请检查 LocalStack/SQS 日志${NC}"
        exit 1
    fi
}

# 等待 LocalStack (4566) 就绪
wait_localstack() {
    local retries=30
    local url="http://localhost:4566/_localstack/health"
    for i in $(seq 1 $retries); do
        if lsof -i:4566 >/dev/null 2>&1; then
            echo -e "${YELLOW}⏳ LocalStack 端口已开启，等待健康检查... ($i/$retries)${NC}"
        else
            echo -e "${YELLOW}⏳ 等待 LocalStack 启动 (端口 4566)... ($i/$retries)${NC}"
        fi
        # health check (community edition returns service map)
        if curl -s "$url" | grep -E '"sqs": "(available|running)"' >/dev/null; then
            echo -e "${GREEN}✅ LocalStack 就绪${NC}"
            return 0
        fi
        sleep 2
    done
    echo -e "${RED}❌ LocalStack 未在预期时间内就绪 (端口 4566)${NC}"
    exit 1
}

# 启动核心 API 服务
start_api_services() {
    echo -e "${YELLOW}🔧 启动核心 API 服务...${NC}"

    # 创建日志目录
    mkdir -p /tmp

    # 激活虚拟环境
    source myenv/bin/activate

    # 启动 YOLO API (8000)
    echo -e "${BLUE}启动 YOLO API (端口 8000)...${NC}"
    nohup uvicorn app:app --reload --host 0.0.0.0 --port 8000 > /tmp/yolo_api.log 2>&1 &
    echo $! > /tmp/yolo_api.pid

    # 启动 OCR API (8001)
    echo -e "${BLUE}启动 OCR API (端口 8001)...${NC}"
    nohup uvicorn app_ocr:app --reload --host 0.0.0.0 --port 8001 > /tmp/ocr_api.log 2>&1 &
    echo $! > /tmp/ocr_api.pid

    # 启动 Workflow API (8002)
    echo -e "${BLUE}启动 Workflow API (端口 8002)...${NC}"
    nohup uvicorn app_workflow:app --reload --host 0.0.0.0 --port 8002 > /tmp/workflow_api.log 2>&1 &
    echo $! > /tmp/workflow_api.pid

    # 启动 Recall API (8003)
    echo -e "${BLUE}启动 Recall API (端口 8003)...${NC}"
    nohup uvicorn app_recall:app --reload --host 0.0.0.0 --port 8003 > /tmp/recall_api.log 2>&1 &
    echo $! > /tmp/recall_api.pid

    echo -e "${GREEN}✅ 核心 API 服务启动完成${NC}"
}

# 启动 Chrome 扩展后端和 Orchestrator
start_extension_backend() {
    echo -e "${YELLOW}🌐 启动 Chrome 扩展后端和 Orchestrator...${NC}"

    cd getcontent/backend

    # 启动前执行数据库迁移，确保 users 等表存在
    echo -e "${BLUE}执行数据库迁移...${NC}"
    local migrate_ok=0
    for i in $(seq 1 5); do
        if node tools/migrate.js; then
            migrate_ok=1
            echo -e "${GREEN}✅ 数据库迁移完成${NC}"
            break
        fi
        echo -e "${YELLOW}⏳ 数据库迁移失败，重试中... ($i/5)${NC}"
        sleep 2
    done
    if [ "$migrate_ok" -ne 1 ]; then
        echo -e "${RED}⚠️  数据库迁移失败，继续启动服务（可能导致登录/用户功能不可用）${NC}"
    fi

    # 启动 GetContent 后端 (8787)
    echo -e "${BLUE}启动 GetContent 后端 (端口 8787)...${NC}"
    nohup node src/index.js > /tmp/getcontent_backend.log 2>&1 &
    echo $! > /tmp/getcontent_backend.pid

    # 等待后端启动
    sleep 2

    # 启动 Orchestrator (8788)
    echo -e "${BLUE}启动 Orchestrator (端口 8788)...${NC}"
    nohup node orchestrator.js > /tmp/orchestrator.log 2>&1 &
    echo $! > /tmp/orchestrator.pid

    cd "$PROJECT_ROOT"

    # 等待服务启动
    sleep 3

    # 创建测试用户
    echo -e "${BLUE}创建测试用户...${NC}"
    cd getcontent/backend
    if node tools/add-user.js test test test_account; then
        echo -e "${GREEN}✅ 测试用户创建成功${NC}"
    else
        echo -e "${RED}⚠️  创建测试用户失败，请检查数据库迁移/表结构（relation users 是否存在）${NC}"
    fi
    cd "$PROJECT_ROOT"

    echo -e "${GREEN}✅ Chrome 扩展后端和 Orchestrator 启动完成${NC}"
}

# 健康检查
health_check() {
    echo -e "${YELLOW}🔍 执行健康检查...${NC}"

    # 等待所有服务完全启动
    echo -e "${YELLOW}等待服务启动完成...${NC}"
    sleep 15

    # 检查各个服务
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

        if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "200"; then
            echo -e "${GREEN}✅ $name 运行正常${NC}"
        else
            echo -e "${RED}❌ $name 连接失败${NC}"
        fi
    done

    # 测试扩展登录
    echo -e "${YELLOW}测试扩展登录...${NC}"
    if curl -s -X POST http://localhost:8787/auth/login \
        -H "Content-Type: application/json" \
        -d '{"username":"test","password":"test"}' | grep -q "account_id"; then
        echo -e "${GREEN}✅ 扩展登录测试成功${NC}"
    else
        echo -e "${RED}❌ 扩展登录测试失败${NC}"
    fi
}

# 显示服务信息
show_service_info() {
    echo -e "${BLUE}"
    echo "========================================"
    echo "🎉 所有服务启动完成！"
    echo "========================================"
    echo -e "${NC}"

    echo -e "${YELLOW}服务端口信息：${NC}"
    echo "• YOLO Detection API:     http://127.0.0.1:8000"
    echo "• OCR API:               http://127.0.0.1:8001"
    echo "• Workflow Generation:    http://127.0.0.1:8002"
    echo "• Recall/Memory API:     http://127.0.0.1:8003"
    echo "• GetContent Backend:    http://127.0.0.1:8787"
    echo "• Orchestrator:          http://127.0.0.1:8788"
    echo "• Traefik Dashboard:     http://127.0.0.1:8080"
    echo ""

    echo -e "${YELLOW}Chrome 扩展设置：${NC}"
    echo "• 扩展目录: $(pwd)/getcontent/extension/"
    echo "• 登录账户: test / test"
    echo "• 后端地址: http://127.0.0.1:8787"
    echo ""

    echo -e "${YELLOW}日志文件：${NC}"
    echo "• YOLO API:        /tmp/yolo_api.log"
    echo "• OCR API:         /tmp/ocr_api.log"
    echo "• Workflow API:    /tmp/workflow_api.log"
    echo "• Recall API:      /tmp/recall_api.log"
    echo "• GetContent:      /tmp/getcontent_backend.log"
    echo "• Orchestrator:    /tmp/orchestrator.log"
    echo ""

    echo -e "${YELLOW}管理命令：${NC}"
    echo "• 停止所有服务: ./scripts/stop_all_services.sh"
    echo "• 查看服务状态: ./scripts/check_services.sh"
    echo "• 重启服务:     ./scripts/restart_services.sh"
    echo ""

    echo -e "${GREEN}✨ 系统准备就绪！您可以开始测试工作流和 Chrome 扩展了。${NC}"
}

# 主执行流程
main() {
    echo -e "${BLUE}开始启动所有服务...${NC}"

    check_venv
    check_docker
    check_dependencies
    start_infrastructure
    start_api_services
    start_extension_backend
    health_check
    show_service_info

    echo -e "${GREEN}🎊 启动完成！${NC}"
}

# 错误处理
trap 'echo -e "${RED}❌ 启动过程中发生错误。请检查日志文件。${NC}"; exit 1' ERR

# 执行主函数
main "$@"
