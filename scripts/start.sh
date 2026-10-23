#!/bin/bash
# scripts/start.sh

set -e

PROFILE=${1:-runtime}

case $PROFILE in
  minimal)
    echo "🚀 Starting minimal services..."
    make up-minimal
    ;;
  runtime|development)
    echo "🚀 Starting runtime services..."
    make up-runtime
    ;;
  full|dev-full)
    echo "🚀 Starting full development environment..."
    make up-dev
    ;;
  platform)
    echo "🚀 Starting ML platform..."
    make up-platform
    ;;
  production)
    echo "🚀 Starting production services..."
    # 生产环境配置
    export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
    make up-runtime
    ;;
  *)
    echo "❌ Unknown profile: $PROFILE"
    echo "Available profiles: minimal, runtime, development, full, platform, production"
    exit 1
    ;;
esac

echo "✅ Services started successfully!"
echo "🌐 API Gateway: http://localhost"
echo "📊 Traefik Dashboard: http://localhost:8080"