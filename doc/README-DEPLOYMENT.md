# 🚀 一体化部署指南

## 快速启动

### 一键自动化部署
```bash
# 完整初始化 (推荐首次使用)
./scripts/bootstrap.sh

# 快速启动 (已初始化环境)
make up-runtime
make smoke
```

## 部署架构概览

### 🏗️ 服务整合成果
- **21个服务 → 1个统一入口** (Traefik API网关)
- **8个API端点 → 统一路由** (`/api/v1/`)
- **复杂启动 → 5种档位** (minimal/runtime/dev-full/platform/web)
- **8000-8007端口 → 仅暴露80/443** (内部网络隔离)

### 📊 服务分层

| 层级 | 服务数量 | 用途 | 启动命令 |
|------|----------|------|----------|
| **infra** | 3个 | 基础设施 (PostgreSQL, LocalStack, Traefik) | `make up-minimal` |
| **runtime** | 5个 | 核心API (YOLO, OCR, Workflow, Recall, Vision) | `make up-runtime` |
| **platform** | 3个 | ML平台 (DPO, Models, A/B) | `make up-platform` |
| **web** | 2个 | Web界面 (Replay UI, GetContent) | `make up-web` |
| **workers** | 7个 | 后台服务 (LLM Worker, Embeddings等) | `make up-dev` |
| **jobs** | 1个 | 定时任务 (Skill Mining) | `make up-dev` |

## 🎯 启动档位选择

### 1. 最小核心 (5分钟验证)
```bash
make up-minimal
# 启动: PostgreSQL + LocalStack + Traefik + YOLO + LLM Worker
# 用途: 基础功能验证，CI/CD最小测试
```

### 2. 运行时服务 (完整API)
```bash
make up-runtime
# 启动: 基础设施 + 所有API服务
# 用途: 日常开发，API集成测试
```

### 3. 完整开发环境
```bash
make up-dev
# 启动: 全部21个服务
# 用途: 功能开发，端到端测试
```

### 4. 专项启动
```bash
make up-platform  # 仅ML训练平台
make up-web       # 仅Web界面
```

## 🌐 API统一访问

### 新的访问方式 (推荐)
```bash
# 统一入口 - 所有API通过网关访问
curl http://localhost/api/v1/vision/yolo/health
curl http://localhost/api/v1/workflow/generate
curl http://localhost/api/v1/ml/dpo/status
```

### 旧的直接访问 (仍可用)
```bash
# 直接端口访问 (仅开发调试)
curl http://localhost:8000/health  # YOLO
curl http://localhost:8001/health  # OCR
curl http://localhost:8002/health  # Workflow
```

## 📋 常用操作

### 服务管理
```bash
# 查看状态
make ps

# 查看日志
make logs                    # 所有服务
make logs SERVICE=yolo-api   # 特定服务

# 重启服务
make down && make up-runtime

# 清理环境
make clean
```

### 健康检查
```bash
# 自动化冒烟测试
make smoke

# 手动API测试
curl http://localhost/api/v1/vision/yolo/health
curl http://localhost:8080/api/overview  # Traefik仪表盘
```

### 初始化管理
```bash
# 重新初始化基础设施
make bootstrap

# 完整重置环境
make clean
./scripts/bootstrap.sh
```

## 🔧 配置管理

### 环境变量
```bash
# 复制并编辑配置
cp .env.example .env
vim .env

# 主要配置项
POSTGRES_PASSWORD=gamepass    # 数据库密码
MOCK_LLM=1                   # LLM模式 (1=Mock, 0=真实)
OPENAI_API_KEY=sk-...        # OpenAI密钥
LOG_LEVEL=info               # 日志级别
```

### Docker Profiles
```bash
# 查看可用profiles
docker compose config --profiles

# 自定义组合启动
docker compose --profile infra --profile runtime --profile web up -d
```

## 🛠️ 故障排除

### 常见问题解决

#### 1. 端口冲突
```bash
# 检查端口占用
lsof -i :80 -i :5432 -i :4566

# 修改端口映射 (docker-compose.override.yml)
```

#### 2. 服务无法启动
```bash
# 查看详细错误
make logs SERVICE=postgres
make logs SERVICE=localstack

# 重置Docker环境
docker system prune -f
make clean
```

#### 3. API路由问题
```bash
# 检查Traefik路由配置
curl http://localhost:8080/api/http/routers

# 测试网关连通性
curl -v http://localhost/api/v1/vision/yolo/health
```

#### 4. 数据库连接失败
```bash
# 检查PostgreSQL状态
docker compose exec postgres pg_isready -U gameuser

# 手动连接测试
docker compose exec postgres psql -U gameuser -d gamedb
```

## 📈 性能优化

### 资源监控
```bash
# 查看容器资源使用
docker stats

# 系统资源
docker system df
```

### 扩容策略
```bash
# 水平扩展LLM Worker
docker compose up --scale llm-worker=3 -d

# 增加资源限制 (编辑docker-compose.yml)
deploy:
  resources:
    limits:
      memory: 2G
      cpus: '1.0'
```

## 🚀 生产部署

### 生产环境准备
```bash
# 生产配置
cp .env.example .env.prod
# 编辑: 修改密码、启用HTTPS、配置真实LLM等

# 生产启动
COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml make up-runtime
```

### 安全配置清单
- [ ] 修改默认数据库密码
- [ ] 配置HTTPS证书
- [ ] 限制Traefik仪表盘访问
- [ ] 启用API认证
- [ ] 配置防火墙规则
- [ ] 设置日志轮转

## 🎉 成功验证

部署成功后，你应该能够：

✅ **统一访问**: `http://localhost/api/v1/` 访问所有API
✅ **服务监控**: `http://localhost:8080` 查看Traefik仪表盘
✅ **健康检查**: `make smoke` 全部通过
✅ **分层启动**: 不同档位按需启动
✅ **日志聚合**: `make logs` 查看所有服务日志

## 📚 更多文档

- [运行手册](docs/runbook.md) - 详细操作指南
- [功能使用指南](USAGE_GUIDE.md) - 各功能使用方法
- [架构演进指南](IMPROVE_USAGE_GUIDE.md) - 13阶段完整路线图

---

🎯 **一句话总结**: 从21个分散服务到1个统一入口，从8个端口到1个网关，从复杂启动到5种档位 - 全部不改任何业务代码！