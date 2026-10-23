One‑Click LocalStack SQS

Run one command to start LocalStack and auto‑create all required queues:

- `make sqs-up` (recommended), or
- `bash scripts/one_click_sqs.sh`

What it does
- Starts `localstack` on `http://localhost:4566`.
- LocalStack runs `config/localstack/10-queues.sh` to create FIFO queues:
  - `llm.request.fifo`
  - `llm.invoke.fifo`
  - `device.demo.hp.fifo`
  - `device.demo.lp.fifo`
  - `device.demo.control.fifo`

Queue URLs
- Full URLs (Node): `http://localhost:4566/000000000000/<queue>`
- Path form (py_consumer): `/000000000000/<queue>`

Verify
- `docker exec -it localstack awslocal sqs list-queues`
- `aws --endpoint-url=http://localhost:4566 sqs list-queues`
- Health: `curl -s http://localhost:4566/health`

Tear down
- `make sqs-down` (or `docker compose -f docker-compose.sqs.yml down`)
