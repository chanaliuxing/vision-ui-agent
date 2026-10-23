#!/bin/bash
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test  
export AWS_REGION=us-east-1
export AWS_ENDPOINT_URL=http://localhost:4566
echo "🚀 MQ Worker starting with LocalStack credentials"
node worker.js
