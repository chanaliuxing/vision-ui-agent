# 🚀 Game Automation Platform 运行手册

## 快速开始

### 1. 首次设置
```bash
# 克隆并进入项目目录
cd .

# 复制环境变量配置
cp .env.example .env

# 编辑配置 (可选)
vim .env

# 初始化基础设施
make bootstrap
```

### 2. 启动服务
```bash
# 最小核心服务 (推荐开始)
make up-minimal

# 运行时服务 (包含所有API)
make up-runtime

# 完整开发环境
make up-dev
```

### 3. 验证部署
```bash
# 运行冒烟测试
make smoke

# 查看服务状态
make ps

# 查看日志
make logs SERVICE=yolo-api
```

## 服务架构

### 分层结构
- **infra**: 基础设施 (PostgreSQL, LocalStack, Traefik)
- **runtime**: 运行时API (YOLO, OCR, Workflow, Recall, Vision)
- **platform**: ML平台 (DPO, Model Manager, A/B Testing)
- **web**: Web界面 (Replay UI, GetContent Backend)
- **workers**: 后台服务 (LLM Worker, Embeddings等)
- **jobs**: 定时任务 (Skill Mining)

### 端口映射
| 服务 | 内部端口 | 外部访问 |
|------|----------|----------|
| API Gateway | 80/443 | http://localhost |
| Traefik Dashboard | 8080 | http://localhost:8080 |
| YOLO API | 8000 | /api/v1/vision/yolo/* |
| OCR API | 8001 | /api/v1/vision/ocr/* |
| Workflow API | 8002 | /api/v1/workflow/* |
| Recall API | 8003 | /api/v1/recall/* |
| DPO Service | 8004 | /api/v1/ml/dpo/* |
| Model Manager | 8005 | /api/v1/ml/models/* |
| A/B Testing | 8006 | /api/v1/ml/experiments/* |
| Vision Analysis | 8007 | /api/v1/vision/analysis/* |

## 常用命令

### 服务管理
```bash
# 启动特定配置
make up-minimal     # 最小核心
make up-runtime     # 运行时服务
make up-platform    # ML平台
make up-web         # Web界面
make up-dev         # 完整环境

# 停止服务
make down

# 重启服务
make down && make up-runtime

# 查看状态
make ps
docker compose ps --services
```

### 日志查看
```bash
# 查看所有日志
make logs

# 查看特定服务日志
make logs SERVICE=yolo-api
make logs SERVICE=llm-worker

# 实时跟踪日志
docker compose logs -f yolo-api

# 查看最近N行日志
docker compose logs --tail=100 yolo-api
```

### 调试工具
```bash
# 进入容器调试
docker compose exec yolo-api bash
docker compose exec postgres psql -U gameuser -d gamedb

# 查看网络连接
docker network ls
docker network inspect game-network

# 查看卷数据
docker volume ls
docker volume inspect game_postgres_data
```

## API使用指南

### 统一访问入口
所有API通过网关统一访问: `http://localhost/api/v1/`

### 认证 (如果启用)
```bash
# 获取JWT Token
curl -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'

# 使用Token访问API
curl -H "Authorization: Bearer $JWT_TOKEN" \
  http://localhost/api/v1/vision/yolo/health
```

### 核心API示例
```bash
# YOLO检测
curl -F "image=@sample.png" \
  "http://localhost/api/v1/vision/yolo/predict"

# OCR识别
curl -F "image=@text.png" \
  "http://localhost/api/v1/vision/ocr/predict"

# 工作流生成
curl -X POST http://localhost/api/v1/workflow/generate \
  -H "Content-Type: application/json" \
  -d '{"task": "自动回复微信消息", "provider": "gemini"}'

# 记忆检索
curl -X POST http://localhost/api/v1/recall/search \
  -H "Content-Type: application/json" \
  -d '{"goal": "login to website", "k": 5}'
```

## 故障排除

### 常见问题

#### 1. 服务无法启动
```bash
# 检查端口占用
lsof -i :80
lsof -i :5432

# 检查Docker资源
docker system df
docker system prune

# 重置环境
make clean
make bootstrap
```

#### 2. 健康检查失败
```bash
# 查看健康检查状态
docker compose ps

# 查看失败原因
make logs SERVICE=postgres
make logs SERVICE=localstack

# 手动测试连接
curl http://localhost:4566/health
pg_isready -h localhost -p 5432 -U gameuser
```

#### 3. API网关路由问题
```bash
# 检查Traefik配置
curl http://localhost:8080/api/overview

# 查看路由规则
curl http://localhost:8080/api/http/routers

# 测试特定路由
curl -v http://localhost/api/v1/vision/yolo/health
```

#### 4. 数据库连接问题
```bash
# 检查PostgreSQL状态
docker compose exec postgres pg_isready -U gameuser

# 连接数据库
docker compose exec postgres psql -U gameuser -d gamedb

# 检查扩展
SELECT * FROM pg_extension WHERE extname = 'vector';
```

#### 5. LocalStack问题
```bash
# 检查LocalStack健康状态
curl http://localhost:4566/health

# 列出SQS队列
aws --endpoint-url=http://localhost:4566 sqs list-queues

# 重新初始化队列
docker compose --profile bootstrap up --force-recreate
```

### 性能优化

#### 1. 资源监控
```bash
# 查看容器资源使用
docker stats

# 查看磁盘使用
docker system df

# 查看网络流量
docker compose exec traefik cat /var/log/traefik/access.log
```

#### 2. 扩容服务
```bash
# 水平扩展Worker
docker compose up --scale llm-worker=3

# 垂直扩展 (增加资源限制)
# 编辑 docker-compose.yml 添加:
# deploy:
#   resources:
#     limits:
#       memory: 2G
#       cpus: '1.0'
```

### 开发调试

#### 1. 热重载开发
```bash
# 启用开发覆盖配置
export COMPOSE_FILE=docker-compose.yml:docker-compose.override.yml

# 挂载代码目录进行热重载
# (需要在override.yml中配置volumes)
```

#### 2. 单独调试服务
```bash
# 停止特定服务
docker compose stop yolo-api

# 本地运行调试
cd .
source myenv/bin/activate
uvicorn app:app --reload --port 8000
```

## 生产部署

### 1. 环境准备
```bash
# 生产环境变量
cp .env.example .env.prod
# 编辑生产配置

# 使用生产配置
export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
```

### 2. 安全配置
- 修改默认密码
- 启用HTTPS
- 配置防火墙
- 限制API访问
- 启用访问日志

### 3. 监控告警
- 配置Prometheus监控
- 设置Grafana仪表盘
- 配置告警规则
- 日志聚合分析

## 备份恢复

### 数据备份
```bash
# 备份PostgreSQL数据
docker compose exec postgres pg_dump -U gameuser gamedb > backup.sql

# 备份LocalStack数据
docker compose exec localstack tar -czf /tmp/localstack-backup.tar.gz /var/lib/localstack
docker compose cp localstack:/tmp/localstack-backup.tar.gz ./
```

### 数据恢复
```bash
# 恢复PostgreSQL
docker compose exec -T postgres psql -U gameuser gamedb < backup.sql

# 恢复LocalStack
docker compose cp ./localstack-backup.tar.gz localstack:/tmp/
docker compose exec localstack tar -xzf /tmp/localstack-backup.tar.gz -C /
```

## 联系支持

如遇到问题，请提供以下信息：
1. 错误信息和日志
2. 服务状态 (`make ps`)
3. 环境配置 (脱敏的.env)
4. 复现步骤

---

📚 更多文档: [USAGE_GUIDE.md](../USAGE_GUIDE.md) | [IMPROVE_USAGE_GUIDE.md](../IMPROVE_USAGE_GUIDE.md)