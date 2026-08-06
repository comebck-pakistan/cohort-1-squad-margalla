/**
 * Evolution API Webhook Handler
 * Receives webhook events from Evolution API and forwards them to the backend.
 * Handles: QRCODE_UPDATED, CONNECTION_UPDATE, MESSAGES_UPSERT
 * Zero business logic — only normalizes payloads and relays.
 */
const axios = require('axios');
const config = require('./config');
const { createLogger, format, transports } = require('winston');

const logger = createLogger({
  level: 'info',
  format: format.combine(format.timestamp(), format.json()),
  transports: [new transports.Console()],
});

// In-memory QR code cache (per instance/store)
const qrCache = new Map();

// Fast local dedup only. Durable idempotency lives in the backend database.
const processedMessageIds = new Set();
const MAX_PROCESSED_IDS = 10000;
const gatewayStartedAtSeconds = Math.floor(Date.now() / 1000);

const VOICE_FALLBACK_MESSAGE =
  "Sorry, I couldn't understand that voice message. Please send it again or type your request.";

/**
 * Map Evolution API connection states to the backend's session status enum.
 * Backend enum: disconnected, initializing, waiting_for_qr, authenticated, connected, reconnecting, failed
 */
function mapConnectionState(evolutionState) {
  switch (evolutionState) {
    case 'open': return 'connected';
    case 'connecting': return 'initializing';
    case 'close': return 'disconnected';
    default: return 'disconnected';
  }
}

/**
 * Validate that the webhook call is from our Evolution API instance.
 * Checks the apikey field in the payload against our configured secret.
 */
function validateWebhook(req) {
  // Prefer the custom header; Evolution also includes the API key in payloads.
  const secret = req.headers['x-webhook-secret'] || req.body?.apikey;
  if (config.webhookSecret && secret !== config.webhookSecret) {
    return false;
  }
  return true;
}

/**
 * Extract store_id from the instance name.
 * Instance names are set to store_id during creation.
 */
function extractStoreId(payload) {
  return payload.instance || null;
}

/**
 * Report session status to the backend.
 */
async function reportStatus(storeId, status, phoneNumber = null, error = null) {
  try {
    await axios.post(`${config.backendUrl}/internal/whatsapp/session-events`, {
      store_id: storeId,
      status,
      phone_number: phoneNumber,
      error,
    }, {
      headers: { 'X-Internal-Token': config.internalToken },
      timeout: 10000,
    });
    logger.info({ msg: 'Status reported to backend', storeId, status });
  } catch (err) {
    logger.warn({ msg: 'Failed to report status to backend', storeId, error: err.message });
  }
}

/**
 * Handle QRCODE_UPDATED event.
 * Caches QR code and reports waiting_for_qr status to backend.
 */
async function handleQRCodeUpdated(payload) {
  const storeId = extractStoreId(payload);
  if (!storeId) return;

  const qrData = payload.data?.qrcode;
  if (!qrData) return;

  // Cache the QR code (prefer base64 image, fall back to raw code)
  const qrBase64 = qrData.base64 || null;
  qrCache.set(storeId, qrBase64);

  logger.info({ msg: 'QR code updated', storeId, hasBase64: !!qrBase64 });
  await reportStatus(storeId, 'waiting_for_qr');
}

/**
 * Handle CONNECTION_UPDATE event.
 * Maps state and reports to backend.
 */
async function handleConnectionUpdate(payload) {
  const storeId = extractStoreId(payload);
  if (!storeId) return;

  const connectionState = payload.data?.connection || payload.data?.state;
  if (!connectionState) return;

  const mappedStatus = mapConnectionState(connectionState);
  logger.info({ msg: 'Connection update', storeId, evolutionState: connectionState, mappedStatus });

  // Clear QR cache when connected
  if (mappedStatus === 'connected') {
    qrCache.delete(storeId);
  }

  await reportStatus(storeId, mappedStatus);
}

/**
 * Handle MESSAGES_UPSERT event.
 * Normalizes to the backend's InternalMessageRequest schema and forwards.
 */
async function handleMessagesUpsert(payload) {
  const storeId = extractStoreId(payload);
  if (!storeId) return;

  const rawData = payload.data;
  const messages = Array.isArray(rawData) ? rawData : [rawData];
  for (const data of messages) {
    await handleSingleMessage(storeId, data);
  }
}

/**
 * Detect the type of WhatsApp message.
 * @param {object} message — data.message from webhook payload
 * @returns {'text'|'image'|'video'|'document'|'audio'|null}
 */
function detectMessageType(message) {
  if (!message) return null;
  if (message.audioMessage) return 'audio';
  if (message.imageMessage) return 'image';
  if (message.videoMessage) return 'video';
  if (message.documentMessage) return 'document';
  if (message.conversation || message.extendedTextMessage) return 'text';
  return null;
}

/**
 * Extract text content from a message (conversation text or media caption).
 * @param {object} message — data.message from webhook payload
 * @returns {string}
 */
function extractTextContent(message) {
  if (!message) return '';
  return message.conversation
    || message.extendedTextMessage?.text
    || message.imageMessage?.caption
    || message.videoMessage?.caption
    || message.documentMessage?.caption
    || '';
}

/**
 * Forward message to backend and send reply back to customer.
 * Shared by text and audio paths to avoid code duplication.
 */
async function forwardAndReply(storeId, customerNumber, messageText, messageType, whatsappMessageId) {
  const res = await axios.post(`${config.backendUrl}/internal/whatsapp/messages`, {
    store_id: storeId,
    customer_number: customerNumber,
    message: messageText,
    message_type: messageType,
    whatsapp_message_id: whatsappMessageId || null,
  }, {
    headers: { 'X-Internal-Token': config.internalToken },
    timeout: 30000,
  });

  // If backend returns a reply and it's not a human-mode-active marker, send it back
  if (res.data?.message && res.data.message !== '[AI disabled - human mode active]') {
    const evolutionClient = require('./evolution-client');

    if (res.data.image_url) {
      await evolutionClient.sendMedia(storeId, customerNumber, res.data.image_url, res.data.message);
    } else {
      await evolutionClient.sendText(storeId, customerNumber, res.data.message);
    }
  }

  return res;
}

/**
 * Process an audio/voice message: download → transcribe → forward transcript.
 */
async function processAudioMessage(storeId, data, customerNumber, whatsappMessageId) {
  const evolutionClient = require('./evolution-client');
  const transcriptionClient = require('./transcription-client');

  try {
    // Step 1: Download media
    logger.info({ msg: 'Processing voice message', storeId, messageId: whatsappMessageId });
    let media;
    try {
      media = await evolutionClient.downloadMediaMessage(storeId, data);
    } catch (downloadErr) {
      logger.error({ msg: 'Audio download failed', storeId, messageId: whatsappMessageId, error: downloadErr.message });
      await evolutionClient.sendText(storeId, customerNumber, VOICE_FALLBACK_MESSAGE);
      return;
    }

    // Step 2: Validate MIME type
    if (!media.mimeType || !media.mimeType.startsWith('audio/')) {
      logger.warn({ msg: 'Unsupported audio MIME type', storeId, messageId: whatsappMessageId, mimeType: media.mimeType });
      await evolutionClient.sendText(storeId, customerNumber, VOICE_FALLBACK_MESSAGE);
      return;
    }

    // Step 3: Validate size
    if (media.buffer.length > config.maxAudioBytes) {
      logger.warn({ msg: 'Audio too large', storeId, messageId: whatsappMessageId, bytes: media.buffer.length, limit: config.maxAudioBytes });
      await evolutionClient.sendText(storeId, customerNumber, VOICE_FALLBACK_MESSAGE);
      return;
    }

    // Step 4: Transcribe
    let transcript;
    try {
      transcript = await transcriptionClient.transcribeAudio({
        buffer: media.buffer,
        mimeType: media.mimeType,
        fileName: media.fileName,
      });
    } catch (transcribeErr) {
      logger.error({ msg: 'Transcription failed', storeId, messageId: whatsappMessageId, error: transcribeErr.message });
      await evolutionClient.sendText(storeId, customerNumber, VOICE_FALLBACK_MESSAGE);
      return;
    }

    // Step 5: Validate transcript not empty
    if (!transcript) {
      logger.warn({ msg: 'Empty transcript', storeId, messageId: whatsappMessageId });
      await evolutionClient.sendText(storeId, customerNumber, VOICE_FALLBACK_MESSAGE);
      return;
    }

    // Step 6: Forward to backend as audio message type
    logger.info({ msg: 'Forwarding transcript to backend', storeId, messageId: whatsappMessageId, transcriptLength: transcript.length });
    await forwardAndReply(storeId, customerNumber, transcript, 'audio', whatsappMessageId);

  } catch (err) {
    // Catch-all: never leak internal errors to customer
    logger.error({ msg: 'Voice message processing error', storeId, messageId: whatsappMessageId, error: err.message });
    try {
      await evolutionClient.sendText(storeId, customerNumber, VOICE_FALLBACK_MESSAGE);
    } catch (sendErr) {
      logger.error({ msg: 'Failed to send voice fallback', storeId, error: sendErr.message });
    }
  }
}

async function handleSingleMessage(storeId, data) {
  if (!data || !data.key) return;

  // Skip messages sent by us
  if (data.key.fromMe) return;

  const skipReason = getSkipReason(data);
  if (skipReason) {
    logger.info({ msg: 'Inbound event skipped', storeId, reason: skipReason });
    return;
  }

  const whatsappMessageId = data.key.id;

  // Idempotency: skip if we've already processed this message ID
  if (whatsappMessageId && processedMessageIds.has(whatsappMessageId)) {
    logger.info({ msg: 'Duplicate message skipped', storeId, messageId: whatsappMessageId });
    return;
  }

  const customerNumber = normalizeCustomerNumber(data);
  if (!customerNumber) {
    logger.info({ msg: 'Message identity could not be normalized', storeId, messageId: whatsappMessageId });
    return;
  }

  const msgType = detectMessageType(data.message);

  // Handle audio/voice messages via transcription pipeline
  if (msgType === 'audio') {
    await processAudioMessage(storeId, data, customerNumber, whatsappMessageId);
    markProcessed(whatsappMessageId);
    return;
  }

  // Extract message text (conversation or caption)
  const messageText = extractTextContent(data.message);

  if (!messageText) {
    logger.info({ msg: 'Non-text message received, skipping', storeId, type: Object.keys(data.message || {}).join(',') });
    return;
  }

  // Determine message type for backend
  const messageType = msgType === 'image' ? 'image'
    : msgType === 'video' ? 'video'
    : msgType === 'document' ? 'document'
    : 'text';

  logger.info({ msg: 'Message received', storeId, from: customerNumber, messageId: whatsappMessageId });

  try {
    await forwardAndReply(storeId, customerNumber, messageText, messageType, whatsappMessageId);
    markProcessed(whatsappMessageId);
  } catch (err) {
    logger.error({ msg: 'Failed to forward message to backend', storeId, error: err.message });
  }
}

function markProcessed(messageId) {
  if (!messageId) return;
  processedMessageIds.add(messageId);
  if (processedMessageIds.size > MAX_PROCESSED_IDS) {
    const iterator = processedMessageIds.values();
    for (let i = 0; i < 1000; i++) {
      const next = iterator.next();
      if (next.done) break;
      processedMessageIds.delete(next.value);
    }
  }
}

function getSkipReason(data, nowSeconds = Math.floor(Date.now() / 1000)) {
  const key = data.key || {};
  const jid = key.remoteJid || '';
  if (jid.endsWith('@g.us')) return 'group';
  if (jid === 'status@broadcast' || jid.endsWith('@broadcast')) return 'broadcast';
  if (jid.endsWith('@newsletter')) return 'newsletter';

  const upsertType = String(data.type || data.upsertType || '').toLowerCase();
  if (['append', 'history', 'history_sync'].includes(upsertType)) return 'history_sync';

  const message = data.message || {};
  const unsupportedKeys = [
    'protocolMessage', 'reactionMessage', 'senderKeyDistributionMessage',
    'pollUpdateMessage', 'keepInChatMessage',
  ];
  if (unsupportedKeys.some((name) => message[name])) return 'protocol_or_reaction';

  const rawTimestamp = data.messageTimestamp?.low
    || data.messageTimestamp
    || data.timestamp
    || 0;
  const timestamp = Number(rawTimestamp);
  const oldestAllowed = Math.max(
    gatewayStartedAtSeconds - 60,
    nowSeconds - config.maxInboundAgeSeconds,
  );
  if (timestamp && timestamp < oldestAllowed) return 'stale';
  return null;
}

function normalizeCustomerNumber(data) {
  const key = data.key || {};
  // Evolution/Baileys supplies the real phone JID as *Alt when the primary
  // identifier is WhatsApp's opaque LID.
  const candidates = [
    key.remoteJidAlt,
    data.remoteJidAlt,
    key.remoteJid,
    key.participantAlt,
    data.participantAlt,
  ].filter(Boolean);
  const jid = candidates.find((value) =>
    value.endsWith('@s.whatsapp.net') || value.endsWith('@c.us')
  );
  if (!jid) return null;
  const number = jid.replace(/@(s\.whatsapp\.net|c\.us)$/, '');
  return /^\d{7,15}$/.test(number) ? number : null;
}

/**
 * Main webhook handler — Express middleware.
 */
function webhookHandler(req, res) {
  const payload = req.body;

  // Validate webhook authenticity
  if (!validateWebhook(req)) {
    logger.warn({ msg: 'Webhook validation failed', ip: req.ip });
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const event = payload.event;
  const storeId = extractStoreId(payload);

  logger.info({ msg: 'Webhook received', event, storeId });

  // Handle events asynchronously — respond immediately to Evolution API
  res.json({ status: 'received' });

  // Process in background
  (async () => {
    try {
      switch (event) {
        case 'qrcode.updated':
        case 'QRCODE_UPDATED':
          await handleQRCodeUpdated(payload);
          break;
        case 'connection.update':
        case 'CONNECTION_UPDATE':
          await handleConnectionUpdate(payload);
          break;
        case 'messages.upsert':
        case 'MESSAGES_UPSERT':
          await handleMessagesUpsert(payload);
          break;
        default:
          logger.info({ msg: 'Unhandled webhook event', event, storeId });
      }
    } catch (err) {
      logger.error({ msg: 'Webhook processing error', event, storeId, error: err.message });
    }
  })();
}

/**
 * Get cached QR code for a store.
 */
function getCachedQR(storeId) {
  return qrCache.get(storeId) || null;
}

module.exports = {
  webhookHandler,
  getCachedQR,
  mapConnectionState,
  getSkipReason,
  normalizeCustomerNumber,
  handleMessagesUpsert,
  detectMessageType,
  extractTextContent,
  processAudioMessage,
  forwardAndReply,
  VOICE_FALLBACK_MESSAGE,
  _processedMessageIds: processedMessageIds,
};
