# Makefile for YOLO Auto-Scaling System
# Provides simple commands for managing the entire system

.PHONY: help build start stop restart status scale logs clean test health
.PHONY: bootstrap up-minimal up-runtime up-dev up-platform up-web down ps smoke

# Default target
help: ## Show this help message
	@echo "YOLO Auto-Scaling System Commands:"
	@echo "=================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Legacy Commands (still available):"
	@echo "  bootstrap   - Initialize databases and queues"
	@echo "  up-minimal  - Start minimal services (infra + yolo + llm-worker)"
	@echo "  up-runtime  - Start runtime services (vision + workflow + memory)"
	@echo "  up-dev      - Start full development environment"
	@echo "  up-platform - Start ML platform services"
	@echo "  up-web      - Start web UI services"
	@echo "  sqs-up      - One-click LocalStack SQS up + bootstrap queues"
	@echo ""
	@echo "Examples:"
	@echo "  make start          # Start all services with auto-scaling"
	@echo "  make scale-5        # Scale to 5 workers"
	@echo "  make status         # Show system status"

# 基础设施初始化
bootstrap:
	@echo "🚀 Bootstrapping infrastructure..."
	docker compose --profile infra up -d
	@echo "⏳ Waiting for services to be ready..."
	sleep 10
	docker compose --profile bootstrap up --remove-orphans
	@echo "✅ Bootstrap completed"

# 最小启动 (5个核心服务)
up-minimal:
	@echo "🚀 Starting minimal services..."
	docker compose --profile infra --profile minimal up -d

# 运行时启动
up-runtime:
	@echo "🚀 Starting runtime services..."
	docker compose --profile infra --profile runtime up -d

# 完整开发环境
up-dev:
	@echo "🚀 Starting full development environment..."
	docker compose --profile infra --profile runtime --profile platform --profile web --profile workers --profile jobs up -d

# 只启动ML平台
up-platform:
	@echo "🚀 Starting ML platform services..."
	docker compose --profile infra --profile platform up -d

# 只启动Web服务
up-web:
	@echo "🚀 Starting web services..."
	docker compose --profile infra --profile web up -d

# 停止所有服务
down:
	@echo "🛑 Stopping all services..."
	docker compose down

# 显示运行状态
ps:
	docker compose ps

# 查看日志
logs:
ifdef SERVICE
	docker compose logs -f $(SERVICE)
else
	docker compose logs -f
endif

# 冒烟测试
smoke:
	@echo "🧪 Running smoke tests..."
	@./scripts/smoke-test.sh

# 清理
clean:
	@echo "🧹 Cleaning up..."
	docker compose down -v
	docker system prune -f

# LocalStack SQS one-click
sqs-up:
	@bash scripts/one_click_sqs.sh

sqs-down:
	@docker compose -f docker-compose.sqs.yml down

sqs-ps:
	@docker compose -f docker-compose.sqs.yml ps

# ============ NEW AUTO-SCALING COMMANDS ============

# BUILD AND SETUP
build: ## Build all Docker images
	@echo "🔨 Building Docker images..."
	docker-compose build
	docker-compose -f scaling/docker-compose.scaling.yml build

install-deps: ## Install Python dependencies
	@echo "📦 Installing dependencies..."
	pip install -r requirements.txt

setup: build install-deps ## Complete setup (build + install)
	@echo "✅ Setup complete!"

# SERVICE MANAGEMENT
start: ## Start all services (base + scaling)
	@echo "🚀 Starting YOLO auto-scaling system..."
	@echo "  Starting infrastructure..."
	docker-compose --profile infra up -d
	@sleep 5
	@echo "  Starting core APIs..."
	docker-compose --profile runtime up -d
	@sleep 3
	@echo "  Starting scaling services..."
	docker-compose -f scaling/docker-compose.scaling.yml --profile scaling up -d
	@echo "✅ All services started!"
	@echo ""
	@make health

start-minimal: ## Start minimal system (without scaling)
	@echo "🚀 Starting minimal YOLO system..."
	docker-compose --profile infra --profile minimal up -d

start-dev: ## Start development environment with all services
	@echo "🚀 Starting full development environment..."
	docker-compose --profile dev-full up -d
	docker-compose -f scaling/docker-compose.scaling.yml --profile dev-scaling up -d

stop: ## Stop all services
	@echo "🛑 Stopping all services..."
	docker-compose -f scaling/docker-compose.scaling.yml down
	docker-compose down

restart: ## Restart all services
	@echo "🔄 Restarting services..."
	@make stop
	@sleep 2
	@make start

# SCALING OPERATIONS
scale-status: ## Show worker scaling status
	@echo "📊 Worker scaling status:"
	python scaling/scale_workers.py status

scale-1: ## Scale to 1 worker
	@echo "⚡ Scaling to 1 worker..."
	python scaling/scale_workers.py scale 1

scale-3: ## Scale to 3 workers
	@echo "⚡ Scaling to 3 workers..."
	python scaling/scale_workers.py scale 3

scale-5: ## Scale to 5 workers
	@echo "⚡ Scaling to 5 workers..."
	python scaling/scale_workers.py scale 5

scale-10: ## Scale to 10 workers
	@echo "⚡ Scaling to 10 workers..."
	python scaling/scale_workers.py scale 10

auto-scale: ## Run one-time auto-scaling
	@echo "🤖 Running auto-scaling..."
	python scaling/scale_workers.py auto

monitor: ## Start continuous monitoring and auto-scaling
	@echo "👁️  Starting continuous monitoring..."
	@echo "   Press Ctrl+C to stop"
	python scaling/scale_workers.py monitor

# MONITORING AND LOGS
status: ## Show system status
	@echo "📊 System Status:"
	@echo "=================="
	@echo ""
	@echo "🏥 Health Checks:"
	@make health-quiet || true
	@echo ""
	@echo "📈 Queue & Workers:"
	@python scaling/scale_workers.py status | head -20

health: ## Check health of all services
	@echo "🏥 Health Checks:"
	@echo "=================="
	@echo -n "YOLO API (8000):     "
	@curl -s http://localhost:8000/health > /dev/null && echo "✅ OK" || echo "❌ FAIL"
	@echo -n "Queue API (8010):    "
	@curl -s http://localhost:8010/health > /dev/null && echo "✅ OK" || echo "❌ FAIL"
	@echo -n "Progress API (8011): "
	@curl -s http://localhost:8011/health > /dev/null && echo "✅ OK" || echo "❌ FAIL"
	@echo -n "Hybrid Router (8020):"
	@curl -s http://localhost:8020/health > /dev/null && echo "✅ OK" || echo "❌ FAIL"

health-quiet: ## Quiet health check (for scripts)
	@curl -s http://localhost:8000/health > /dev/null
	@curl -s http://localhost:8010/health > /dev/null
	@curl -s http://localhost:8011/health > /dev/null

logs-scaling: ## Show scaling service logs
	@echo "📋 Scaling Service Logs:"
	docker-compose -f scaling/docker-compose.scaling.yml logs --tail=50

logs-workers: ## Show worker logs
	docker-compose -f scaling/docker-compose.scaling.yml logs -f yolo-worker

logs-queue: ## Show queue service logs
	docker-compose -f scaling/docker-compose.scaling.yml logs -f queue-api

# TESTING
test-simple: ## Test with simple request (fast path)
	@echo "🧪 Testing simple request (should use fast path)..."
	@echo "Creating test image..."
	@python -c "import base64; print(base64.b64encode(b'test-image-data').decode())" > /tmp/test_image.txt
	@curl -X POST http://localhost:8020/v1/pick \
		-H "Content-Type: application/json" \
		-d '{"image":{"base64":"'$$(cat /tmp/test_image.txt)'"},"context":{"goal":"test"},"idempotency_key":"test-simple"}' \
		| python -m json.tool

test-complex: ## Test with complex request (queue path)
	@echo "🧪 Testing complex request (should use queue path)..."
	@python -c "import base64; print(base64.b64encode(b'x' * 1000000).decode())" > /tmp/test_large_image.txt
	@curl -X POST http://localhost:8020/v1/pick \
		-H "Content-Type: application/json" \
		-d '{"image":{"base64":"'$$(cat /tmp/test_large_image.txt)'"},"context":{"goal":"complex test"},"options":{"max_candidates":50},"idempotency_key":"test-complex"}' \
		| python -m json.tool

test-route: ## Test routing decisions
	@echo "🧪 Testing routing decisions..."
	@echo "Simple request (should be fast path):"
	@curl -s "http://localhost:8020/route/test?max_candidates=5&image_size_kb=100&timeout_ms=2000" | python -m json.tool
	@echo ""
	@echo "Complex request (should be queue path):"
	@curl -s "http://localhost:8020/route/test?max_candidates=50&image_size_kb=800&timeout_ms=8000" | python -m json.tool

# UTILITIES
purge-queue: ## Purge all jobs from queue (DANGEROUS!)
	@echo "⚠️  This will delete ALL pending jobs!"
	@read -p "Are you sure? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	python scaling/scale_workers.py purge --confirm

clean-scaling: ## Clean up scaling containers and volumes
	@echo "🧹 Cleaning up scaling services..."
	docker-compose -f scaling/docker-compose.scaling.yml down -v

reset: clean start ## Full reset (clean + start)
	@echo "🔄 System reset complete!"

# CONFIGURATION
config-show: ## Show current routing configuration
	@echo "⚙️  Current routing configuration:"
	@curl -s http://localhost:8020/route/config | python -m json.tool

config-fast: ## Set aggressive fast-path thresholds
	@echo "⚙️  Setting aggressive fast-path configuration..."
	@curl -X POST http://localhost:8020/route/config \
		-H "Content-Type: application/json" \
		-d '{"max_candidates":50,"image_size_kb":1000,"timeout_ms":10000,"complexity_score":5.0}'

config-conservative: ## Set conservative fast-path thresholds
	@echo "⚙️  Setting conservative fast-path configuration..."
	@curl -X POST http://localhost:8020/route/config \
		-H "Content-Type: application/json" \
		-d '{"max_candidates":10,"image_size_kb":200,"timeout_ms":3000,"complexity_score":2.0}'

# ALIASES
up: start ## Alias for start
