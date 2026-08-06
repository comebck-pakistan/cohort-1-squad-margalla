/**
 * Evolution API HTTP Client
 * Thin wrapper around Evolution API v2.3.7 REST endpoints.
 * Zero business logic — only translates between this adapter and Evolution API.
 */
const axios = require('axios');
const config = require('./config');
const { createLogger, format, transports } = require('winston');

const logger = createLogger({
  level: 'info',
  format: format.combine(format.timestamp(), format.json()),
  transports: [new transports.Console()],
});

const api = axios.create({
  baseURL: config.evolutionApiUrl,
  headers: {
    'Content-Type': 'application/json',
    'apikey': config.evolutionApiKey,
  },
  timeout: 30000,
});

/**
 * Create a new Evolution API instance for a store.
 * Configures webhook to point to this adapter's webhook endpoint.
 * @param {string} storeId — used as the instance name
 * @returns {Promise<object>} — Evolution API response (includes QR if qrcode: true)
 */
async function createInstance(storeId) {
  logger.info({ msg: 'Creating Evolution API instance', storeId });
  const response = await api.post('/instance/create', {
    instanceName: storeId,
    integration: 'WHATSAPP-BAILEYS',
    qrcode: true,
    webhook: {
      enabled: true,
      url: config.evolutionWebhookUrl,
      byEvents: false,
      base64: true,
      headers: {
        'X-Webhook-Secret': config.webhookSecret,
      },
      events: [
        'QRCODE_UPDATED',
        'CONNECTION_UPDATE',
        'MESSAGES_UPSERT',
      ],
    },
  });
  return response.data;
}

/**
 * Connect an existing instance (triggers QR code generation).
 * @param {string} storeId
 * @returns {Promise<object>} — includes QR code data if in connecting state
 */
async function connectInstance(storeId) {
  logger.info({ msg: 'Connecting Evolution API instance', storeId });
  const response = await api.get(`/instance/connect/${storeId}`);
  return response.data;
}

/**
 * Get the current connection state for an instance.
 * @param {string} storeId
 * @returns {Promise<object>} — { instance, state } where state is 'open', 'connecting', or 'close'
 */
async function getConnectionState(storeId) {
  const response = await api.get(`/instance/connectionState/${storeId}`);
  return response.data;
}

/**
 * Send a text message via an instance.
 * @param {string} storeId
 * @param {string} to — recipient phone number (without @s.whatsapp.net)
 * @param {string} text — message body
 * @returns {Promise<object>}
 */
async function sendText(storeId, to, text) {
    try {
      const payload = {
        number: to,
        text: text,
        delay: 1200,
      };

      const res = await api.post(`/message/sendText/${storeId}`, payload, {
        headers: {
          'apikey': config.evolutionApiKey
        }
      });
      return res.data;
    } catch (error) {
      logger.error({ 
        msg: 'Failed to send text message', 
        storeId, 
        to,
        error: error.response?.data || error.message 
      });
      throw error;
    }
  }

  /**
   * Send a media message (e.g. image) via Evolution API
   */
  async function sendMedia(storeId, to, mediaUrl, caption) {
    try {
      // If mediaUrl is a relative path like /uploads/..., prepend backend URL
      let finalMediaUrl = mediaUrl;
      if (mediaUrl.startsWith('/')) {
        finalMediaUrl = `${config.backendUrl}${mediaUrl}`;
      }

      const payload = {
        number: to,
        mediatype: 'image',
        caption: caption || '',
        media: finalMediaUrl,
        delay: 1200,
      };

      const res = await api.post(`/message/sendMedia/${storeId}`, payload, {
        headers: {
          'apikey': config.evolutionApiKey
        }
      });
      return res.data;
    } catch (error) {
      logger.error({ 
        msg: 'Failed to send media message', 
        storeId, 
        to,
        mediaUrl,
        error: error.response?.data || error.message 
      });
      throw error;
    }
  }

/**
 * Delete/destroy an instance.
 * @param {string} storeId
 * @returns {Promise<object>}
 */
async function deleteInstance(storeId) {
  logger.info({ msg: 'Deleting Evolution API instance', storeId });
  try {
    const response = await api.delete(`/instance/delete/${storeId}`);
    return response.data;
  } catch (err) {
    // Instance might not exist — that's okay
    if (err.response?.status === 404) {
      logger.warn({ msg: 'Instance not found during delete (already gone)', storeId });
      return { status: 'not_found' };
    }
    throw err;
  }
}

/**
 * Check if Evolution API is reachable.
 * @returns {Promise<boolean>}
 */
async function isHealthy() {
  try {
    const response = await api.get('/instance/fetchInstances', { timeout: 5000 });
    return response.status === 200;
  } catch {
    return false;
  }
}

/**
 * Fetch all instances to check if one already exists.
 * @param {string} storeId
 * @returns {Promise<object|null>}
 */
async function fetchInstance(storeId) {
  try {
    const response = await api.get('/instance/fetchInstances', {
      params: { instanceName: storeId },
    });
    const instances = Array.isArray(response.data) ? response.data : [];
    return instances.find(i => i.name === storeId || i.instance?.instanceName === storeId) || null;
  } catch {
    return null;
  }
}

/**
 * Download media from a received message as a Buffer.
 * Uses the Evolution API getBase64FromMediaMessage endpoint.
 * @param {string} storeId — instance name
 * @param {object} messageData — the full message data object from the webhook
 * @returns {Promise<{buffer: Buffer, mimeType: string, fileName: string}>}
 */
async function downloadMediaMessage(storeId, messageData) {
  const messageId = messageData?.key?.id;
  if (!messageId) {
    throw new Error('Message data missing key.id for media download');
  }

  logger.info({ msg: 'Downloading media message', storeId, messageId });

  const response = await api.post(`/chat/getBase64FromMediaMessage/${storeId}`, {
    message: {
      key: {
        id: messageId,
      },
    },
  }, {
    timeout: 30000,
  });

  const data = response.data;
  if (!data || !data.base64) {
    throw new Error('Evolution API returned empty or malformed media response');
  }

  let base64String = data.base64;
  let mimeType = data.mimetype || data.mimeType || 'audio/ogg';

  // Strip data-URL prefix if present (e.g., "data:audio/ogg;base64,...")
  const dataUrlMatch = base64String.match(/^data:([^;]+);base64,(.+)$/);
  if (dataUrlMatch) {
    mimeType = dataUrlMatch[1];
    base64String = dataUrlMatch[2];
  }

  const buffer = Buffer.from(base64String, 'base64');

  // Derive a safe filename from the message ID
  const ext = mimeType.split('/')[1] || 'ogg';
  const fileName = `voice_${messageId}.${ext}`;

  // Never log buffer/base64 content
  logger.info({ msg: 'Media downloaded', storeId, messageId, mimeType, bytes: buffer.length });

  return { buffer, mimeType, fileName };
}

module.exports = {
  createInstance,
  connectInstance,
  getConnectionState,
  sendText,
  sendMedia,
  downloadMediaMessage,
  deleteInstance,
  isHealthy,
  fetchInstance,
};
