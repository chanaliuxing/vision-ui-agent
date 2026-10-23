#!/usr/bin/env python3
# scripts/send_control.py

import os, json, sys
import boto3

if len(sys.argv) < 3:
    print("Usage: python scripts/send_control.py <PAUSE|RESUME|STOP> <run_id>")
    sys.exit(1)

device = os.getenv("DEVICE_ID", "demo")
cmd = sys.argv[1].upper()     # PAUSE | RESUME | STOP
run_id = sys.argv[2]

# 队列名格式
if device.startswith("device-"):
    queue = f"{device}-control.fifo"
else:
    queue = f"device-{device}-control.fifo"

sqs = boto3.client(
    "sqs",
    region_name=os.getenv("AWS_REGION", "us-east-1"),
    endpoint_url=os.getenv("AWS_ENDPOINT_URL")
)

try:
    url = sqs.get_queue_url(QueueName=queue)["QueueUrl"]
    body = json.dumps({"cmd": cmd, "run_id": run_id})

    sqs.send_message(
        QueueUrl=url,
        MessageBody=body,
        MessageGroupId=device,
        MessageDeduplicationId=f"{run_id}-{cmd}-{int(os.times().elapsed)}"
    )
    print(f"Sent {cmd} command for run_id={run_id} to queue={queue}")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)