Old Tool Runbook (One-Click + Services)

Overview
- DB: Restored into your local Postgres (`.env: DATABASE=postgresql://postgres:postgres@localhost:5432/postgres`).
- Node API: `oldTool/chat_orchestrator_service/server.js` on port 6000.
- Python Consumer: `oldTool/chat_orchestrator_service/py_consumer/start_consumer.py` (SQS + HTTP).
- Python WeChat Automation: `oldTool/wechat_automation_service/engine.py`.
- SQS: One‑click LocalStack with auto‑created queues.

Prerequisites
- Docker + Docker Compose
- Node 18+ and npm
- Python 3.10+ (use `myenv`) and Postgres running locally
- WeChat desktop app (grant macOS Accessibility permissions to Python when using GUI automation)

One‑Click SQS
- Start: `make sqs-up` (or `bash scripts/one_click_sqs.sh`)
- Verify health: `curl -s http://localhost:4566/health`
- List queues:
  - `docker exec -it localstack awslocal sqs list-queues`
  - or `aws --endpoint-url=http://localhost:4566 sqs list-queues`
- Stop: `make sqs-down` (status: `make sqs-ps`)

SQS Queue URLs and Env Exports
- Node (full URLs):
  - `export MQ_SQS_ENDPOINT=http://localhost:4566`
  - `export MQ_SQS_QUEUE_LLM_COMPLETE=http://localhost:4566/000000000000/device.demo.hp.fifo`
- Python py_consumer (path form):
  - `export MQ_SQS_ENDPOINT=http://localhost:4566`
  - `export MQ_SQS_REGION=us-east-1`
  - `export MQ_TYPE=sqs`
  - `export MQ_SQS_QUEUE_LLM_REQUEST=/000000000000/llm.request.fifo`
  - `export MQ_SQS_QUEUE_LLM_INVOKE=/000000000000/llm.invoke.fifo`
  - `export MQ_SQS_QUEUE_LLM_COMPLETE=/000000000000/device.demo.hp.fifo`

Start Services (Order)
1) Postgres
   - Check: `psql "postgresql://postgres:postgres@localhost:5432/postgres" -c "select now()"`

2) Node Orchestrator (port 6000)
   - `cd oldTool/chat_orchestrator_service`
   - Install deps: `npm ci` (or `npm install`)
   - Run: `node server.js`
   - Health: `curl -s http://localhost:6000/api/health || curl -s http://localhost:6000/health`
   - Notes: requires `OPENAI_API_KEY` (and optionally `DEEPSEEK_API_KEY`).

3) Python Consumer (SQS + HTTP /llm-request)
   - `cd oldTool/chat_orchestrator_service/py_consumer`
   - Install deps (file may be UTF‑16):
     - `pip install -r requirements.txt`
     - If encoding error: `iconv -f utf-16 -t utf-8 requirements.txt > requirements.utf8.txt && pip install -r requirements.utf8.txt`
   - Env:
     - `export PG_DSN=postgresql://postgres:postgres@localhost:5432/postgres`
     - `export MQ_TYPE=sqs`
     - `export MQ_SQS_ENDPOINT=http://localhost:4566`
     - `export MQ_SQS_REGION=us-east-1`
     - `export MQ_SQS_QUEUE_LLM_REQUEST=/000000000000/llm.request.fifo`
     - `export MQ_SQS_QUEUE_LLM_INVOKE=/000000000000/llm.invoke.fifo`
     - `export MQ_SQS_QUEUE_LLM_COMPLETE=/000000000000/device.demo.hp.fifo`
   - Run: `python start_consumer.py`

4) Python WeChat Automation
   - `cd oldTool/wechat_automation_service`
   - `source ../../myenv/bin/activate`
   - Run: `python engine.py`
   - Ensure `.env` has `API_BASE_URL=http://localhost:6000/api`

DB Restore & Verify (already done)
- Import: `python scripts/sql_loader.py -v --file "oldTool/全备份-postgres-202507082022.sql"`
- Verify: `python scripts/verify_sql_load.py` (see `artifacts/verify_sql_load.out`)

Troubleshooting
- Node demands OPENAI key: export a dummy for startup (e.g., `OPENAI_API_KEY=sk-test`).
- py_consumer MQ fallback: if LocalStack not running or queues missing, it serves HTTP‑only mode on `PY_CONSUMER_PORT` (default 8001).
- Queue mismatch: Node uses full URLs; Python uses path (concatenated with endpoint internally).

