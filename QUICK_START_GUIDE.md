# AI自动化系统快速上手指南
# Quick Start Guide for AI Automation System

## 🚀 5分钟快速启动 / 5-Minute Quick Start

### 1. 环境准备 / Environment Setup

```bash
# 克隆项目并进入目录
cd .

# 创建虚拟环境
python -m venv myenv && source myenv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑.env文件，设置必要的API密钥
```

### 2. 数据库初始化 / Database Initialization

```bash
# 创建数据库（确保PostgreSQL已安装）
createdb automation_db
psql automation_db -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 运行迁移
psql automation_db -f db/migrations/sprint_h_rag_reflexion.sql
psql automation_db -f db/migrations/sprint_i_dpo_rlaif.sql
psql automation_db -f db/migrations/sprint_j_skills_macros.sql
psql automation_db -f db/migrations/sprint_k_multimodal.sql
```

### 3. 启动核心服务 / Start Core Services

```bash
# 一键启动所有服务
chmod +x start_all_services.sh
./start_all_services.sh

# 或手动启动核心服务
yolo模型api启动：source ~/yolovenv/bin/activate
cd .
uvicorn app:app --reload --port 8000 # YOLO检测

uvicorn app:app --reload --port 8000 &          # YOLO检测
uvicorn app_ocr:app --reload --port 8001 &      # OCR识别
uvicorn app_workflow:app --reload --port 8002 & # 工作流
python app_replay.py &                          # Web界面
```

### 4. 验证安装 / Verify Installation

```bash
# 检查服务状态
curl http://localhost:8000/health  # YOLO API
curl http://localhost:8001/health  # OCR API
curl http://localhost:8002/health  # Workflow API

# 访问Web界面
open http://localhost:8890
```

## 📖 基础使用 / Basic Usage

### 运行第一个工作流 / Run Your First Workflow

```bash
# 生成简单工作流
python tools/run_workflow_gen.py \
  --task "访问Google搜索页面并搜索AI" \
  --provider gemini \
  --out flows/google_search.json

# 执行工作流
python run_workflow.py \
  --workflow flows/google_search.json \
  --endpoint http://127.0.0.1:8000
```

### 使用高级功能 / Using Advanced Features

#### 启用记忆功能 / Enable Memory Features

```bash
# 启动记忆相关服务
uvicorn server.services.recall_api:app --reload --port 8003 &
python -m server.services.embeddings &

# 运行带记忆的工作流
python run_workflow.py \
  --workflow flows/login.json \
  --enable-memory \
  --recall-threshold 0.7
```

#### 使用技能库 / Using Skill Library

```bash
# 加载技能包
python tools/wf_sprint_j.py load-package --path skills/web_automation.wfpack

# 运行宏增强的工作流
python run_workflow.py \
  --workflow flows/with_macros.json \
  --macro-path skills/
```

#### 自适应执行 / Adaptive Execution

```bash
# 启动自适应服务
uvicorn vision.services.vision_api:app --reload --port 8007 &
python -m adaptive.engines.adaptive_executor &

# 运行自适应工作流
python run_workflow.py \
  --workflow flows/adaptive.json \
  --adaptive-mode \
  --strategy-selection auto
```

## 🛠️ 常用命令 / Common Commands

### 服务管理 / Service Management

```bash
# 启动所有服务
./start_all_services.sh

# 停止所有服务
pkill -f uvicorn
pkill -f "python -m"

# 重启特定服务
pkill -f "app:app"
uvicorn app:app --reload --port 8000 &

# 查看服务状态
ps aux | grep uvicorn
lsof -i :8000-8007
```

### 健康检查 / Health Checks

```bash
# 快速健康检查
./health_check.sh

# 手动检查各服务
for port in {8000..8007}; do
  echo "检查端口 $port: $(curl -s http://localhost:$port/health || echo '❌')"
done
```

### 日志查看 / Log Viewing

```bash
# 查看实时日志
tail -f logs/ai_automation.log

# 查看错误日志
grep ERROR logs/ai_automation.log | tail -20

# 查看特定服务日志
grep "recall_api" logs/ai_automation.log
```

## 🔧 Sprint功能快速使用 / Quick Sprint Features Usage

### Sprint H: 记忆与反思 / Memory & Reflexion

```bash
# 测试记忆召回
python tools/wf_sprint_h.py test-recall \
  --goal "登录LinkedIn" \
  --k 5

# 生成嵌入向量
python tools/wf_sprint_h.py generate-embeddings \
  --plan-ids 1,2,3

# 在工作流中使用记忆
{
  "do": "mem.recall",
  "goal": "登录网站",
  "k": 5
}
```

### Sprint I: 训练与优化 / Training & Optimization

```bash
# 生成训练数据
python tools/wf_sprint_i.py generate-pairs \
  --host example.com \
  --goal login

# 启动DPO训练
python tools/wf_sprint_i.py train \
  --dataset data/pairs.json \
  --epochs 3

# 创建A/B测试
python tools/wf_sprint_i.py ab-test create \
  --name strategy_test \
  --config ab_config.json
```

### Sprint J: 技能与宏 / Skills & Macros

```bash
# 查看技能库状态
python tools/wf_sprint_j.py registry-status

# 挖掘新技能
python tools/wf_sprint_j.py mine-skills \
  --host linkedin.com \
  --min-support 0.3

# 测试宏执行
python tools/wf_sprint_j.py test-macro \
  --name login_sequence \
  --dry-run
```

### Sprint K: 多模态与自适应 / Multimodal & Adaptive

```bash
# 分析页面布局
python tools/wf_sprint_k.py analyze-page \
  --screenshot page.png \
  --save-analysis

# 自适应执行测试
python tools/wf_sprint_k.py adaptive-run \
  --context test_context.json \
  --dry-run

# 查看反馈分析
python tools/wf_sprint_k.py feedback analyze \
  --days 7 \
  --export-report
```

## 📝 配置示例 / Configuration Examples

### 基础环境配置 / Basic Environment Config

```bash
# .env文件最小配置
DATABASE_URL=postgresql://user:pass@localhost:5432/automation_db
LLM_PROVIDER=gemini
LLM_MODEL=gemini-1.5-flash
GEMINI_API_KEY=your-api-key
YOLO_WEIGHTS=weights/best.pt
```

### 工作流JSON示例 / Workflow JSON Examples

#### 简单自动化 / Simple Automation

```json
{
  "name": "Google搜索",
  "start": "search",
  "states": {
    "search": {
      "actions": [
        {"do": "goto", "url": "https://google.com"},
        {"do": "autostep", "instruction": "点击搜索框"},
        {"do": "type_text", "text": "AI自动化"},
        {"do": "autostep", "instruction": "点击搜索按钮"}
      ]
    }
  }
}
```

#### 高级工作流 / Advanced Workflow

```json
{
  "name": "智能登录",
  "start": "smart_login",
  "states": {
    "smart_login": {
      "actions": [
        {
          "do": "mem.recall",
          "goal": "登录{site_name}",
          "k": 3
        },
        {
          "do": "macro.execute",
          "name": "login_sequence",
          "params": {
            "username": "{username}",
            "password": "{password}"
          }
        },
        {
          "do": "adaptive.run",
          "strategy": "auto"
        },
        {
          "do": "plan.reflect",
          "focus": "success_analysis"
        }
      ]
    }
  }
}
```

## 🚨 故障排除快速指南 / Quick Troubleshooting

### 常见问题解决 / Common Issues Solutions

#### 服务无法启动 / Service Won't Start

```bash
# 检查端口占用
lsof -i :8000
kill -9 <PID>

# 检查依赖
pip install -r requirements.txt --force-reinstall

# 检查Python版本
python --version  # 需要3.8+
```

#### 数据库连接失败 / Database Connection Failed

```bash
# 检查PostgreSQL状态
sudo systemctl status postgresql

# 测试连接
psql -h localhost -U automation_user -d automation_db -c "SELECT 1;"

# 重置密码
sudo -u postgres psql -c "ALTER USER automation_user PASSWORD 'new_password';"
```

#### API调用失败 / API Call Failed

```bash
# 检查API密钥
echo $GEMINI_API_KEY

# 测试网络连接
curl -I https://api.openai.com/v1/models

# 查看详细错误
export DEBUG=true
python run_workflow.py --debug
```

### 性能优化 / Performance Optimization

```bash
# 启用缓存
export REDIS_URL=redis://localhost:6379

# 增加工作进程
uvicorn app:app --workers 4

# 监控资源使用
htop
iostat -x 1
```

## 📚 更多资源 / Additional Resources

### 文档链接 / Documentation Links

- **完整系统文档**: [SYSTEM_DOCUMENTATION.md](./SYSTEM_DOCUMENTATION.md)
- **项目配置**: [CLAUDE.md](./CLAUDE.md)
- **Sprint K规格**: [upgrade_sprint_k.md](./upgrade_sprint_k.md)

### 示例项目 / Example Projects

```bash
# 社交媒体自动化
flows/linkedin_automation.json
flows/twitter_posting.json

# 电商自动化
flows/shopping_automation.json
flows/price_monitoring.json

# 内容管理
flows/content_publishing.json
flows/data_collection.json
```

### API端点快速参考 / API Endpoints Quick Reference

| 服务 | 端口 | 端点 | 功能 |
|------|------|------|------|
| YOLO | 8000 | `/predict` | 目标检测 |
| OCR | 8001 | `/predict` | 文字识别 |
| Workflow | 8002 | `/generate` | 工作流生成 |
| Recall | 8003 | `/recall` | 记忆召回 |
| DPO | 8004 | `/train` | 模型训练 |
| Model | 8005 | `/deploy` | 模型部署 |
| A/B Test | 8006 | `/experiments` | 实验管理 |
| Vision | 8007 | `/analyze` | 视觉分析 |

### 获取帮助 / Getting Help

```bash
# CLI工具帮助
python tools/wf_sprint_h.py --help
python tools/wf_sprint_i.py --help
python tools/wf_sprint_j.py --help
python tools/wf_sprint_k.py --help

# 查看API文档
curl http://localhost:8000/docs  # Swagger UI
curl http://localhost:8000/redoc # ReDoc
```

---

**快速上手指南版本**: v1.0.0
**适用系统版本**: Sprint H/I/J/K完整版
**更新日期**: 2024年12月

💡 **提示**: 如遇到问题，请先查看日志文件 `logs/ai_automation.log`，大部分问题都能从日志中找到解决线索。