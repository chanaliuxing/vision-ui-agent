#!/bin/bash
# scripts/bootstrap.sh
# 一键初始化整个项目环境

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# 检查依赖
check_dependencies() {
    log_step "Checking dependencies..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed!"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
        log_error "Docker Compose is not installed!"
        exit 1
    fi

    if ! command -v make &> /dev/null; then
        log_error "Make is not installed!"
        exit 1
    fi

    log_info "✅ All dependencies are available"
}

# 初始化环境配置
init_env() {
    log_step "Initializing environment configuration..."

    if [ ! -f .env ]; then
        cp .env.example .env
        log_info "✅ Created .env from template"
    else
        log_warn "⚠️ .env already exists, skipping"
    fi
}

# 创建必要目录
create_directories() {
    log_step "Creating necessary directories..."

    directories=(
        "out/screens"
        "out/logs"
        "out/reports"
        "weights"
        "flows"
        "config/prometheus"
        "config/nginx"
        "logs"
    )

    for dir in "${directories[@]}"; do
        mkdir -p "$dir"
        log_info "✅ Created directory: $dir"
    done
}

# 下载示例文件
download_examples() {
    log_step "Setting up example files..."

    # 创建示例工作流
    if [ ! -f flows/example.json ]; then
        cat > flows/example.json << 'EOF'
{
  "name": "Example Workflow",
  "start": "detect",
  "states": {
    "detect": {
      "actions": [
        {"do": "autostep", "goal": "click login button"}
      ],
      "transitions": [
        {"go_to": "complete"}
      ]
    },
    "complete": {
      "actions": []
    }
  }
}
EOF
        log_info "✅ Created example workflow"
    fi

    # 创建示例图片 (如果需要)
    if [ ! -f sample.png ]; then
        log_warn "⚠️ sample.png not found, please add a sample image for testing"
    fi
}

# 构建Docker镜像
build_images() {
    log_step "Building Docker images..."

    # 创建基础Dockerfile (如果不存在)
    if [ ! -f Dockerfile ]; then
        cat > Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 默认命令
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
EOF
        log_info "✅ Created basic Dockerfile"
    fi

    # 创建requirements.txt (如果不存在)
    if [ ! -f requirements.txt ]; then
        cat > requirements.txt << 'EOF'
fastapi==0.104.1
uvicorn==0.24.0
psycopg2-binary==2.9.7
boto3==1.29.0
redis==5.0.1
pydantic==2.5.0
python-multipart==0.0.6
aiofiles==23.2.0
httpx==0.25.0
EOF
        log_info "✅ Created basic requirements.txt"
    fi

    log_info "🏗️ Building images... (this may take a while)"
    docker compose build --no-cache
    log_info "✅ Images built successfully"
}

# 初始化基础设施
init_infrastructure() {
    log_step "Initializing infrastructure..."

    # 启动基础设施
    make bootstrap

    log_info "✅ Infrastructure initialized"
}

# 验证部署
verify_deployment() {
    log_step "Verifying deployment..."

    # 等待服务启动
    log_info "⏳ Waiting for services to start..."
    sleep 30

    # 运行冒烟测试
    if [ -f scripts/smoke-test.sh ]; then
        make smoke
    else
        log_warn "⚠️ Smoke test script not found, skipping validation"
    fi
}

# 显示完成信息
show_completion() {
    log_step "Setup completed!"

    echo ""
    echo "🎉 Game Automation Platform is ready!"
    echo ""
    echo "📋 Quick Start Commands:"
    echo "  make up-minimal    # Start minimal services"
    echo "  make up-runtime    # Start runtime services"
    echo "  make up-dev        # Start full development environment"
    echo "  make ps            # Show service status"
    echo "  make logs          # Show all logs"
    echo "  make smoke         # Run smoke tests"
    echo ""
    echo "🌐 Access Points:"
    echo "  API Gateway:       http://localhost"
    echo "  Traefik Dashboard: http://localhost:8080"
    echo "  PostgreSQL:        localhost:5432"
    echo "  LocalStack:        localhost:4566"
    echo ""
    echo "📚 Documentation:"
    echo "  Runbook:           docs/runbook.md"
    echo "  Usage Guide:       USAGE_GUIDE.md"
    echo "  Improve Guide:     IMPROVE_USAGE_GUIDE.md"
    echo ""
}

# 主函数
main() {
    echo "🚀 Starting Game Automation Platform Bootstrap"
    echo ""

    check_dependencies
    init_env
    create_directories
    download_examples
    build_images
    init_infrastructure
    verify_deployment
    show_completion
}

# 如果直接运行此脚本
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi