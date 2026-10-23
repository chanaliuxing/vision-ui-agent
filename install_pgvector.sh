#!/bin/bash

# PostgreSQL pgvector 扩展安装脚本
# 适用于macOS系统

set -e

echo "🔧 PostgreSQL pgvector 扩展安装脚本"
echo "======================================"

# 检查PostgreSQL安装
if [ -d "/Library/PostgreSQL/16" ]; then
    PG_VERSION="16"
    PG_PATH="/Library/PostgreSQL/16"
    echo "✅ 发现 PostgreSQL $PG_VERSION 安装在 $PG_PATH"
else
    echo "❌ 未找到 PostgreSQL 安装"
    echo "请确保 PostgreSQL 已正确安装"
    exit 1
fi

# 方法1: 通过Homebrew安装 (推荐)
echo ""
echo "方法1: 通过 Homebrew 安装 pgvector"
echo "-----------------------------------"
echo "请手动执行以下命令:"
echo ""
echo "# 1. 接受Xcode许可 (如果需要)"
echo "sudo xcodebuild -license accept"
echo ""
echo "# 2. 安装pgvector"
echo "brew install pgvector"
echo ""

# 方法2: 从源码编译
echo "方法2: 从源码编译安装"
echo "-------------------"
echo "如果Homebrew方法不可用，请手动执行:"
echo ""
echo "# 1. 下载源码"
echo "git clone --branch v0.5.1 https://github.com/pgvector/pgvector.git"
echo "cd pgvector"
echo ""
echo "# 2. 设置PostgreSQL路径"
echo "export PATH=\"$PG_PATH/bin:\$PATH\""
echo ""
echo "# 3. 编译安装"
echo "make"
echo "sudo make install"
echo ""

# 方法3: 预编译包 (如果可用)
echo "方法3: 检查是否有预编译包"
echo "-----------------------"
echo "检查PostgreSQL扩展目录:"
echo "ls $PG_PATH/share/postgresql/extension/ | grep vector"
echo ""

# 验证安装
echo "安装完成后验证:"
echo "---------------"
echo "1. 连接到PostgreSQL:"
echo "   psql -h localhost -U postgres -d postgres"
echo ""
echo "2. 创建扩展:"
echo "   CREATE EXTENSION IF NOT EXISTS vector;"
echo ""
echo "3. 验证扩展:"
echo "   \\dx vector"
echo ""

echo "💡 提示: 安装完成后，重新运行 ./scripts/start_all_services.sh"