/**
 * WhatsApp Gateway Configuration
 * Evolution API adapter — transport only, zero business logic.
 */
const config = {
  port: process.env.GATEWAY_PORT || 3001,
  backendUrl: process.env.BACKEND_URL || 'http://localhost:8000',
  internalToken: process.env.INTERNAL_SERVICE_TOKEN || 'dev-internal-token',

  // Evolution API
  evolutionApiUrl: process.env.EVOLUTION_API_URL || 'http://localhost:8080',
  evolutionApiKey: process.env.EVOLUTION_API_KEY || '',
  evolutionWebhookUrl: process.env.EVOLUTION_WEBHOOK_URL || 'http://localhost:3001/webhook/evolution',
  evolutionApiVersion: process.env.EVOLUTION_API_VERSION || '2.3.7',

  // Webhook security: shared secret that Evolution API includes in webhook payloads
  // This is the same as evolutionApiKey — Evolution API sends it in the 'apikey' field of webhook payloads
  webhookSecret: process.env.EVOLUTION_API_KEY || '',
  // Ignore history-sync/reconnect traffic. Live notifications normally arrive
  // within seconds; this allows a small delivery/retry window.
  maxInboundAgeSeconds: Number(process.env.MAX_INBOUND_AGE_SECONDS || 300),

  // Voice-message transcription (Gemini — reuses the same API key as backend)
  geminiApiKey: process.env.GEMINI_API_KEY || '',
  transcriptionModel: process.env.TRANSCRIPTION_MODEL || 'gemini-2.5-flash',
  maxAudioBytes: Number(process.env.MAX_AUDIO_BYTES || 10485760), // 10 MB
  transcriptionTimeoutMs: Number(process.env.TRANSCRIPTION_TIMEOUT_MS || 45000),

  // Image-message vision analysis (Gemini — reuses the same API key as backend)
  visionModel: process.env.VISION_MODEL || 'gemini-2.5-flash',
  maxImageBytes: Number(process.env.MAX_IMAGE_BYTES || 10485760), // 10 MB
  maxImagePixels: Number(process.env.MAX_IMAGE_PIXELS || 25000000), // 25 MP
  visionTimeoutMs: Number(process.env.VISION_TIMEOUT_MS || 45000),

  // Send delay injected into Evolution sendText/sendMedia payloads (ms).
  // Evolution simulates typing for this duration before sending.
  // Default 0 — no artificial delay. Clamped to [0, 5000].
  sendDelayMs: Math.max(0, Math.min(5000, Number(process.env.WHATSAPP_SEND_DELAY_MS || 0) || 0)),

  // Whether to embed base64 media data in Evolution webhooks.
  // false (default) = webhooks carry metadata only; gateway fetches media on demand.
  // true = Evolution embeds full base64 in webhook payloads (causes large payloads).
  webhookBase64: process.env.WEBHOOK_BASE64 === 'true',
};

module.exports = config;
