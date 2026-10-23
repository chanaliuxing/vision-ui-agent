#!/bin/bash

# Start MQ Worker for LLM Vision Processing
# Keeps the process running in background

echo "🚀 Starting MQ Worker for LLM Vision Processing"

# Set AWS credentials for LocalStack
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_REGION=us-east-1
export AWS_ENDPOINT_URL=http://localhost:4566

# Set Node environment
export NODE_ENV=development

echo "✅ AWS credentials configured for LocalStack"
echo "📡 Connecting to queues:"
echo "   - llm-vision-request.fifo"
echo "   - llm-vision-response.fifo"

# Start worker and keep it running
node worker.js &
WORKER_PID=$!

echo "🔄 MQ Worker started with PID: $WORKER_PID"
echo "📝 Worker logs will show MQ processing activity"

# Save PID to file for later management
echo $WORKER_PID > mq_worker.pid

# Keep script running to monitor worker
while kill -0 $WORKER_PID 2>/dev/null; do
    sleep 5
done

echo "❌ MQ Worker stopped"
rm -f mq_worker.pid