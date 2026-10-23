#!/bin/bash

# 将Homebrew安装的pgvector扩展配置到PostgreSQL 16
# 需要sudo权限

set -e

echo "🔧 配置 pgvector 扩展到 PostgreSQL 16"
echo "======================================"

# 检查源文件
HOMEBREW_VECTOR_CONTROL="/opt/homebrew/share/postgresql@14/extension/vector.control"
HOMEBREW_VECTOR_SQL="/opt/homebrew/share/postgresql@14/extension/vector--0.7.4.sql"
HOMEBREW_VECTOR_SO="/opt/homebrew/lib/postgresql@14/vector.so"

# 目标目录
PG16_EXT_DIR="/Library/PostgreSQL/16/share/postgresql/extension"
PG16_LIB_DIR="/Library/PostgreSQL/16/lib/postgresql"

echo "检查源文件..."
if [ ! -f "$HOMEBREW_VECTOR_CONTROL" ]; then
    echo "❌ 未找到 vector.control 文件"
    echo "请确保已通过 brew install pgvector 安装"
    exit 1
fi

echo "✅ 找到 Homebrew pgvector 文件"

# 检查是否有权限
if [ ! -w "$PG16_EXT_DIR" ]; then
    echo "❌ 需要 sudo 权限来复制文件到 PostgreSQL 目录"
    echo "请手动执行以下命令:"
    echo ""
    echo "sudo cp /opt/homebrew/share/postgresql@14/extension/vector.* $PG16_EXT_DIR/"
    echo "sudo cp /opt/homebrew/lib/postgresql@14/vector.so $PG16_LIB_DIR/"
    echo ""
    echo "然后重启 PostgreSQL 服务"
    exit 1
fi

echo "复制扩展文件..."
# 这部分需要sudo权限，用户需要手动执行

echo "请手动执行以下命令来完成安装:"
echo ""
echo "# 1. 复制扩展控制文件"
echo "sudo cp /opt/homebrew/share/postgresql@14/extension/vector.* $PG16_EXT_DIR/"
echo ""
echo "# 2. 复制共享库文件"
echo "sudo cp /opt/homebrew/lib/postgresql@14/vector.so $PG16_LIB_DIR/"
echo ""
echo "# 3. 重启 PostgreSQL 服务"
echo "sudo brew services restart postgresql@16  # 如果通过brew管理"
echo "# 或者重启系统中的PostgreSQL服务"
echo ""
echo "# 4. 验证安装"
echo "psql -h localhost -U postgres -d postgres -c \"CREATE EXTENSION IF NOT EXISTS vector;\""