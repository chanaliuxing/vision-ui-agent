#!/usr/bin/env sh
set -euo pipefail

echo "[init] Creating SQS FIFO queues via awslocal..."

# awslocal is available inside the LocalStack container
awslocal sqs create-queue --queue-name llm.request.fifo --attributes FifoQueue=true,ContentBasedDeduplication=true >/dev/null 2>&1 || true
awslocal sqs create-queue --queue-name llm.invoke.fifo  --attributes FifoQueue=true,ContentBasedDeduplication=true >/dev/null 2>&1 || true
awslocal sqs create-queue --queue-name device.demo.hp.fifo      --attributes FifoQueue=true,ContentBasedDeduplication=true >/dev/null 2>&1 || true
awslocal sqs create-queue --queue-name device.demo.lp.fifo      --attributes FifoQueue=true,ContentBasedDeduplication=true >/dev/null 2>&1 || true
awslocal sqs create-queue --queue-name device.demo.control.fifo --attributes FifoQueue=true,ContentBasedDeduplication=true >/dev/null 2>&1 || true

echo "[init] Queues ready:"
awslocal sqs list-queues || true

