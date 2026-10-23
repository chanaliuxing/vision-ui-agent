#!/bin/bash

# 完整的pgvector安装脚本 - 复制所有必要文件
echo "🔧 完成pgvector扩展设置..."

# 检查源文件目录
SOURCE_DIR="/opt/homebrew/Cellar/pgvector/0.8.1/share/postgresql@14/extension"
TARGET_DIR="/Library/PostgreSQL/16/share/postgresql/extension"
LIB_SOURCE="/opt/homebrew/Cellar/pgvector/0.8.1/lib/postgresql@14/vector.so"
LIB_TARGET="/Library/PostgreSQL/16/lib/postgresql/"

echo "需要用sudo执行以下命令来完成pgvector设置："
echo ""
echo "# 1. 复制所有扩展SQL文件"
echo "sudo cp $SOURCE_DIR/vector*.sql $TARGET_DIR/"
echo ""
echo "# 2. 复制control文件（如果还没有）"
echo "sudo cp $SOURCE_DIR/vector.control $TARGET_DIR/"
echo ""
echo "# 3. 复制共享库文件"
echo "sudo cp $LIB_SOURCE $LIB_TARGET"
echo ""
echo "# 4. 重启PostgreSQL服务（如果需要）"
echo "# sudo launchctl stop com.edb.launchd.postgresql-16"
echo "# sudo launchctl start com.edb.launchd.postgresql-16"
echo ""
echo "执行完成后运行以下命令验证："
echo "python scripts/bootstrap_infrastructure.py"