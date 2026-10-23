#!/usr/bin/env python3
"""Bootstrap SQS queues for Stage 3"""

import os, json
import boto3

region = os.getenv("AWS_REGION", "us-east-1")
endpoint = os.getenv("AWS_ENDPOINT_URL")

sqs = boto3.client("sqs", region_name=region, endpoint_url=endpoint)

def ensure_fifo(name: str):
    # FIFO 队列名必须以 .fifo 结尾
    attrs = {
        "FifoQueue": "true",
        "ContentBasedDeduplication": "true",  # 可用内容去重
        "ReceiveMessageWaitTimeSeconds": "0"  # 我们的动作是"非阻塞拉取"，保持 0
    }
    try:
        url = sqs.create_queue(QueueName=name, Attributes=attrs)["QueueUrl"]
        print("created:", name, url)
    except sqs.exceptions.QueueNameExists:
        url = sqs.get_queue_url(QueueName=name)["QueueUrl"]
        print("exists:", name, url)
    return url

if __name__ == "__main__":
    # 旧格式队列（兼容）
    ensure_fifo("device-demo-hp.fifo")
    ensure_fifo("device-demo-lp.fifo")

    # 新格式多应用队列（Stage 5）
    ensure_fifo("device-demo-wechat-hp.fifo")
    ensure_fifo("device-demo-wechat-lp.fifo")
    ensure_fifo("device-demo-slack-hp.fifo")
    ensure_fifo("device-demo-slack-lp.fifo")

    # LLM 请求队列
    ensure_fifo("llm-request.fifo")

    # Stage 6: 控制队列
    ensure_fifo("device-demo-control.fifo")