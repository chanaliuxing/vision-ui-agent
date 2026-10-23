#!/bin/bash

# YOLO+LLM 系统重启脚本
# 停止所有服务然后重新启动

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔄 YOLO+LLM 系统重启脚本${NC}"
echo -e "${BLUE}======================================${NC}"

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${YELLOW}步骤 1/2: 停止所有服务...${NC}"
./scripts/stop_all_services.sh

echo ""
echo -e "${YELLOW}等待 5 秒钟...${NC}"
sleep 5

echo ""
echo -e "${YELLOW}步骤 2/2: 启动所有服务...${NC}"
./scripts/start_all_services.sh

echo ""
echo -e "${GREEN}🎊 系统重启完成！${NC}"