/**
 * Vision LLM Request Handler
 * Processes visual reasoning requests from the MQ system
 */
import { OpenAI } from "openai";
import fetch from 'node-fetch';

// LLM clients
const openaiClient = process.env.OPENAI_API_KEY ? new OpenAI({
  apiKey: process.env.OPENAI_API_KEY
}) : null;

const deepseekClient = process.env.DEEPSEEK_API_KEY ? new OpenAI({
  apiKey: process.env.DEEPSEEK_API_KEY,
  baseURL: process.env.DEEPSEEK_API_URL || 'https://api.deepseek.com/v1'
}) : null;

const nvidiaClient = process.env.NVIDIA_API_KEY ? new OpenAI({
  apiKey: process.env.NVIDIA_API_KEY,
  baseURL: process.env.NVIDIA_API_URL || 'https://integrate.api.nvidia.com/v1'
}) : null;

const ollamaClient = new OpenAI({
  apiKey: process.env.OLLAMA_API_KEY || 'ollama',
  baseURL: process.env.OLLAMA_BASE_URL ? `${process.env.OLLAMA_BASE_URL.replace(/\/$/, '')}/v1` : 'http://127.0.0.1:11434/v1'
});

/**
 * Download image from URL (signed URL from storage)
 */
async function downloadImage(url) {
  try {
    if (url.startsWith('file://')) {
      // Local file for development
      const fs = await import('fs');
      const filePath = url.replace('file://', '');
      return fs.readFileSync(filePath);
    } else {
      // HTTP/HTTPS URL (signed S3/MinIO URL)
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      return await response.buffer();
    }
  } catch (error) {
    console.warn(`⚠️ Failed to download image ${url}:`, error.message);
    return null;
  }
}

/**
 * Process vision data: download images and convert to base64
 */
async function processVisionData(visionArray) {
  if (!visionArray || !Array.isArray(visionArray)) {
    return [];
  }

  const processedVision = [];

  for (const item of visionArray) {
    try {
      if (item.uri) {
        console.log(`📥 Downloading vision item: ${item.role} from ${item.uri}`);
        const imageBytes = await downloadImage(item.uri);

        if (imageBytes) {
          const base64Data = imageBytes.toString('base64');
          processedVision.push({
            type: "image_url",
            image_url: {
              url: `data:image/png;base64,${base64Data}`
            }
          });
        } else {
          console.warn(`⚠️ Skipping failed image download: ${item.uri}`);
        }
      } else if (item.base64) {
        // Already base64 encoded
        processedVision.push({
          type: "image_url",
          image_url: {
            url: `data:image/png;base64,${item.base64}`
          }
        });
      }
    } catch (error) {
      console.warn(`⚠️ Error processing vision item:`, error.message);
    }
  }

  console.log(`📊 Processed ${processedVision.length}/${visionArray.length} vision items`);
  return processedVision;
}

/**
 * Get LLM client based on provider
 */
function getLLMClient(provider) {
  switch (provider?.toLowerCase()) {
    case 'openai':
      if (!openaiClient) throw new Error('OpenAI API key not configured');
      return openaiClient;

    case 'deepseek':
    case 'deepseek_v3':
      if (!deepseekClient) throw new Error('DeepSeek API key not configured');
      return deepseekClient;

    case 'nvidia':
      if (!nvidiaClient) throw new Error('NVIDIA API key not configured');
      return nvidiaClient;

    case 'ollama':
      return ollamaClient;

    default:
      // Default fallback: local ollama first, then cloud providers
      if (ollamaClient) return ollamaClient;
      if (openaiClient) return openaiClient;
      if (deepseekClient) return deepseekClient;
      if (nvidiaClient) return nvidiaClient;
      throw new Error('No LLM provider configured');
  }
}

/**
 * Get appropriate model for provider
 */
function getModelForProvider(provider, customModel = null) {
  if (customModel) return customModel;

  switch (provider?.toLowerCase()) {
    case 'openai':
      return 'gpt-4o-mini';
    case 'deepseek':
    case 'deepseek_v3':
      return 'deepseek-v3';
    case 'nvidia':
      return 'deepseek-ai/deepseek-r1';
    case 'ollama':
      return process.env.AUTOSTEP_VISION_MODEL || process.env.OLLAMA_MODEL || 'qwen3.5:4b';
    default:
      return process.env.AUTOSTEP_VISION_MODEL || process.env.OLLAMA_MODEL || 'qwen3.5:4b';
  }
}

/**
 * Main vision request processor
 *
 * Expected request format:
 * {
 *   request_id: "req_abc123",
 *   provider: "openai"|"deepseek"|"nvidia",
 *   model: "gpt-4o-mini" (optional),
 *   messages: [...], // OpenAI compatible messages
 *   vision: [{uri: "https://...", role: "crop", meta: {...}}, ...],
 *   timeout: 120,
 *   created_at: timestamp
 * }
 */
export async function processVisionRequest(request) {
  const { request_id, provider, model, messages, vision, timeout = 120 } = request;

  console.log(`🎯 Vision request ${request_id}: provider=${provider}, vision_items=${vision?.length || 0}`);

  try {
    // Get LLM client
    const client = getLLMClient(provider);
    const modelName = getModelForProvider(provider, model);

    console.log(`🔍 LLM-MQ: Using ${provider}/${modelName} for ${request_id}`);

    // Process vision data (download images, convert to base64)
    const processedVision = await processVisionData(vision);

    // Build final messages with vision content
    const enhancedMessages = [...messages];

    if (processedVision.length > 0 && enhancedMessages.length > 0) {
      // Add vision content to the last user message
      const lastMessage = enhancedMessages[enhancedMessages.length - 1];
      if (lastMessage.role === 'user') {
        // Ensure content is an array for multimodal
        if (typeof lastMessage.content === 'string') {
          lastMessage.content = [
            { type: 'text', text: lastMessage.content }
          ];
        }

        // Add all vision items
        lastMessage.content = lastMessage.content.concat(processedVision);
      }
    }

    console.log(`🚀 LLM-MQ: Sending request ${request_id} to ${provider} (${enhancedMessages.length} messages, ${processedVision.length} images)`);

    // Call LLM with timeout
    const response = await Promise.race([
      client.chat.completions.create({
        model: modelName,
        messages: enhancedMessages,
        temperature: 0.1,
        max_tokens: 4000
      }),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('LLM timeout')), timeout * 1000)
      )
    ]);

    const content = response.choices[0]?.message?.content || '';
    console.log(`📥 LLM-MQ: Response received for ${request_id} (${content.length} chars)`);

    // Log what was sent/received (truncated for security)
    console.log(`🔍 LLM-MQ REQUEST ${request_id}:`, JSON.stringify({
      provider,
      model: modelName,
      message_count: enhancedMessages.length,
      vision_count: processedVision.length,
      request_chars: JSON.stringify(enhancedMessages).length
    }));

    console.log(`📥 LLM-MQ RESPONSE ${request_id}:`, JSON.stringify({
      response_chars: content.length,
      usage: response.usage,
      content_preview: content.slice(0, 100) + (content.length > 100 ? '...' : '')
    }));

    return {
      content,
      usage: response.usage,
      model: response.model || modelName
    };

  } catch (error) {
    console.error(`❌ Vision request ${request_id} failed:`, error.message);

    return {
      content: '',
      error: error.message,
      error_type: error.name
    };
  }
}
