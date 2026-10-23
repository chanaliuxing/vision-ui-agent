import { SQSClient, ReceiveMessageCommand, DeleteMessageCommand, SendMessageCommand, GetQueueUrlCommand } from "@aws-sdk/client-sqs";
import { routeAndValidate } from "./router.js";
import { processVisionRequest } from "./vision_handler.js";

const region = process.env.AWS_REGION || "us-east-1";
const endpoint = process.env.AWS_ENDPOINT_URL || undefined; // LocalStack 用 http://localhost:4566
const sqs = new SQSClient({ region, endpoint });

async function getUrl(name) {
  const r = await sqs.send(new GetQueueUrlCommand({ QueueName: name }));
  return r.QueueUrl;
}

async function sendToDeviceHP(deviceTarget, body) {
  // deviceTarget 可能是 "demo" 或 "demo.wechat" 格式
  let qname;
  if (deviceTarget.includes('.')) {
    // 新格式：device.demo.wechat -> device-demo-wechat-hp.fifo
    const parts = deviceTarget.split('.');
    qname = `device-${parts.join('-')}-hp.fifo`;
  } else {
    // 兼容旧格式：demo -> device-demo-wechat-hp.fifo (默认wechat)
    qname = `device-${deviceTarget}-wechat-hp.fifo`;
  }

  const QueueUrl = await getUrl(qname);
  const payload = JSON.stringify(body);
  await sqs.send(new SendMessageCommand({
    QueueUrl,
    MessageBody: payload,
    MessageGroupId: deviceTarget.replace('.', '-'),
    MessageDeduplicationId: Buffer.from(payload).toString("base64").slice(0, 128)
  }));
}

// 处理传统 LLM 工作流请求
async function loopLLMWorkflow() {
  const reqUrl = await getUrl("llm-request.fifo");
  console.log("[worker] listening LLM workflow", reqUrl);

  while (true) {
    const resp = await sqs.send(new ReceiveMessageCommand({
      QueueUrl: reqUrl,
      MaxNumberOfMessages: 1,
      WaitTimeSeconds: 3,
      VisibilityTimeout: 20
    }));
    const msgs = resp.Messages || [];
    if (msgs.length === 0) continue;

    for (const m of msgs) {
      const body = JSON.parse(m.Body);
      try {
        const out = await routeAndValidate(body);
        const device = body.device_target || "demo";
        const result = {
          type: "llm.complete",
          job: body.job,
          job_id: body.job_id,
          contact_name: out.contact_name,
          reply_text: out.reply_text,
          audit_rows: out.audit_rows || []
        };
        await sendToDeviceHP(device, result);
        await sqs.send(new DeleteMessageCommand({ QueueUrl: reqUrl, ReceiptHandle: m.ReceiptHandle }));
        console.log("[worker] done workflow job", body.job_id, "-> device", device);
      } catch (e) {
        console.error("[worker] workflow error", e);
      }
    }
  }
}

// 处理新的视觉推理请求
async function loopVisionLLM() {
  const reqUrl = await getUrl("llm-vision-request.fifo");
  const respUrl = await getUrl("llm-vision-response.fifo");
  console.log("[worker] listening LLM vision", reqUrl, "->", respUrl);

  while (true) {
    const resp = await sqs.send(new ReceiveMessageCommand({
      QueueUrl: reqUrl,
      MaxNumberOfMessages: 1,
      WaitTimeSeconds: 10,  // 更长的轮询，减少空查询
      VisibilityTimeout: 60  // 视觉推理可能需要更长时间
    }));
    const msgs = resp.Messages || [];
    if (msgs.length === 0) continue;

    for (const m of msgs) {
      try {
        const body = JSON.parse(m.Body);
        console.log(`[worker] 🎯 Processing vision request ${body.request_id} provider=${body.provider}`);

        const t_start = Date.now();
        const result = await processVisionRequest(body);
        const latency_ms = Date.now() - t_start;

        // 发送响应到 response 队列
        const response = {
          request_id: body.request_id,
          content: result.content || "",
          error: result.error || null,
          latency_ms,
          processed_at: new Date().toISOString()
        };

        await sqs.send(new SendMessageCommand({
          QueueUrl: respUrl,
          MessageBody: JSON.stringify(response),
          MessageGroupId: body.request_id,
          MessageDeduplicationId: `${body.request_id}-${Date.now()}`
        }));

        // ACK 原始请求
        await sqs.send(new DeleteMessageCommand({
          QueueUrl: reqUrl,
          ReceiptHandle: m.ReceiptHandle
        }));

        console.log(`[worker] 📥 Vision request ${body.request_id} completed in ${latency_ms}ms`);

      } catch (e) {
        console.error("[worker] vision error", e);
        // 对于解析错误等致命问题，删除消息避免无限重试
        if (e instanceof SyntaxError) {
          await sqs.send(new DeleteMessageCommand({
            QueueUrl: reqUrl,
            ReceiptHandle: m.ReceiptHandle
          }));
        }
      }
    }
  }
}

async function loop() {
  // 并发处理两种类型的请求
  await Promise.all([
    loopLLMWorkflow(),
    loopVisionLLM()
  ]);
}

loop().catch(e => {
  console.error("[worker] fatal", e);
  process.exit(1);
});