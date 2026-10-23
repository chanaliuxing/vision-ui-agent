#!/usr/bin/env bash
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)

echo "🚀 Starting LocalStack SQS (one-click) ..."
docker compose -f "$root/docker-compose.sqs.yml" up -d

echo "⏳ Waiting for LocalStack health ..."
for i in {1..40}; do
  if curl -fsS http://localhost:4566/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "📜 Queues present:"
# Prefer awslocal inside container if available, otherwise use host AWS CLI
cid=$(docker compose -f "$root/docker-compose.sqs.yml" ps -q localstack || true)
if [ -n "$cid" ]; then
  docker exec "$cid" awslocal sqs list-queues || true
else
  aws --endpoint-url=http://localhost:4566 sqs list-queues || true
fi

cat <<EOF

✅ SQS is ready.

Recommended env exports

Node (full URLs):
  export MQ_SQS_ENDPOINT=http://localhost:4566
  export MQ_SQS_QUEUE_LLM_COMPLETE=http://localhost:4566/000000000000/device.demo.hp.fifo

Python py_consumer (path form):
  export MQ_SQS_ENDPOINT=http://localhost:4566
  export MQ_SQS_REGION=us-east-1
  export MQ_TYPE=sqs
  export MQ_SQS_QUEUE_LLM_REQUEST=/000000000000/llm.request.fifo
  export MQ_SQS_QUEUE_LLM_INVOKE=/000000000000/llm.invoke.fifo
  export MQ_SQS_QUEUE_LLM_COMPLETE=/000000000000/device.demo.hp.fifo

Verify:
  aws --endpoint-url=http://localhost:4566 sqs get-queue-attributes \
    --queue-url http://localhost:4566/000000000000/llm.request.fifo --attribute-names QueueArn
  aws --endpoint-url=http://localhost:4566 sqs get-queue-attributes \
    --queue-url http://localhost:4566/000000000000/llm.invoke.fifo --attribute-names QueueArn
  aws --endpoint-url=http://localhost:4566 sqs get-queue-attributes \
    --queue-url http://localhost:4566/000000000000/device.demo.hp.fifo --attribute-names QueueArn

EOF

