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

  // Extract message text
  const messageText = data.message?.conversation
    || data.message?.extendedTextMessage?.text
    || data.message?.imageMessage?.caption
    || data.message?.videoMessage?.caption
    || data.message?.documentMessage?.caption
    || '';

  if (!messageText) {
    logger.info({ msg: 'Non-text message received, skipping', storeId, type: Object.keys(data.message || {}).join(',') });
    return;
  }

  // Determine message type
  const messageType = data.message?.imageMessage ? 'image'
    : data.message?.videoMessage ? 'video'
    : data.message?.documentMessage ? 'document'
    : 'text';

  logger.info({ msg: 'Message received', storeId, from: customerNumber, messageId: whatsappMessageId });

  try {
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
  _processedMessageIds: processedMessageIds,
};
