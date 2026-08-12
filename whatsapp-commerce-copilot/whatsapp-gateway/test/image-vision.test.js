/**
 * Image Vision Integration Tests
 * All external calls (Evolution API, vision client, backend, WhatsApp send) are mocked.
 * Tests the full image pipeline: detect → download → validate → analyze → forward → reply.
 */
const test = require('node:test');
const assert = require('node:assert/strict');

const NOW = Math.floor(Date.now() / 1000);

function makeImagePayload({ caption, id = 'msg-image-001', mimetype = 'image/jpeg' } = {}) {
  const imageMessage = { mimetype };
  if (caption !== undefined) imageMessage.caption = caption;
  return {
    instance: 'store-123',
    event: 'messages.upsert',
    data: {
      key: {
        id,
        fromMe: false,
        remoteJid: '923001234567@s.whatsapp.net',
      },
      messageTimestamp: NOW,
      message: { imageMessage },
    },
  };
}

function setupMocks() {
  delete require.cache[require.resolve('../src/webhook-handler')];
  delete require.cache[require.resolve('../src/evolution-client')];
  delete require.cache[require.resolve('../src/vision-client')];
  delete require.cache[require.resolve('../src/config')];

  const mockConfig = {
    port: 3001,
    backendUrl: 'http://localhost:8000',
    internalToken: 'test-token',
    evolutionApiUrl: 'http://localhost:8080',
    evolutionApiKey: 'test-key',
    evolutionWebhookUrl: 'http://localhost:3001/webhook/evolution',
    evolutionApiVersion: '2.3.7',
    webhookSecret: 'test-key',
    maxInboundAgeSeconds: 300,
    geminiApiKey: 'test-gemini-key',
    visionModel: 'gemini-2.5-flash',
    maxImageBytes: 10485760,
    maxImagePixels: 25000000,
    visionTimeoutMs: 45000,
  };
  require.cache[require.resolve('../src/config')] = {
    id: require.resolve('../src/config'),
    filename: require.resolve('../src/config'),
    loaded: true,
    exports: mockConfig,
  };

  const calls = {
    downloadMedia: [],
    analyzeImage: [],
    sendText: [],
    sendMedia: [],
    backendPost: [],
  };

  const mockEvolutionClient = {
    downloadMediaMessage: async (storeId, messageData) => {
      calls.downloadMedia.push({ storeId, messageData });
      return {
        buffer: Buffer.from('fake-image-data'),
        mimeType: 'image/jpeg',
        fileName: 'media_msg-image-001.jpeg',
      };
    },
    sendText: async (storeId, to, text) => {
      calls.sendText.push({ storeId, to, text });
      return {};
    },
    sendMedia: async (storeId, to, url, caption) => {
      calls.sendMedia.push({ storeId, to, url, caption });
      return {};
    },
  };
  require.cache[require.resolve('../src/evolution-client')] = {
    id: require.resolve('../src/evolution-client'),
    filename: require.resolve('../src/evolution-client'),
    loaded: true,
    exports: mockEvolutionClient,
  };

  const mockVisionClient = {
    analyzeImage: async ({ buffer, mimeType, fileName, caption }) => {
      calls.analyzeImage.push({ bufferLength: buffer.length, mimeType, fileName, caption });
      return {
        description: 'A black athletic-style running shoe',
        text_ocr: 'NIKE',
        attributes: ['black', 'athletic', 'shoe', 'sneaker'],
        confidence: 0.92,
        safety_status: 'safe',
      };
    },
  };
  require.cache[require.resolve('../src/vision-client')] = {
    id: require.resolve('../src/vision-client'),
    filename: require.resolve('../src/vision-client'),
    loaded: true,
    exports: mockVisionClient,
  };

  const originalAxios = require('axios');
  const mockAxiosPost = async (url, data, opts) => {
    if (url.includes('/internal/whatsapp/messages')) {
      calls.backendPost.push({ url, data });
      return {
        data: {
          message: 'We have the Black Runner in stock!',
          intent: 'product_search',
          confidence: 0.9,
          store_id: data.store_id,
        },
      };
    }
    return originalAxios.post(url, data, opts);
  };
  const axiosModule = require.cache[require.resolve('axios')];
  const originalPost = axiosModule.exports.post;
  axiosModule.exports.post = mockAxiosPost;

  const webhookHandler = require('../src/webhook-handler');

  return {
    webhookHandler,
    mockConfig,
    mockEvolutionClient,
    mockVisionClient,
    calls,
    cleanup: () => {
      axiosModule.exports.post = originalPost;
      webhookHandler._processedMessageIds.clear();
      delete require.cache[require.resolve('../src/webhook-handler')];
      delete require.cache[require.resolve('../src/evolution-client')];
      delete require.cache[require.resolve('../src/vision-client')];
      delete require.cache[require.resolve('../src/config')];
    },
  };
}

// ========== IMAGE MESSAGE TESTS ==========

test('image with caption: download → analyze → forward vision context → reply', async () => {
  const { webhookHandler, calls, cleanup } = setupMocks();
  try {
    await webhookHandler.handleMessagesUpsert(makeImagePayload({ caption: 'Ye joota available hai?' }));

    assert.equal(calls.downloadMedia.length, 1);
    assert.equal(calls.analyzeImage.length, 1);
    assert.equal(calls.analyzeImage[0].caption, 'Ye joota available hai?');

    assert.equal(calls.backendPost.length, 1);
    const body = calls.backendPost[0].data;
    assert.equal(body.message_type, 'image');
    assert.equal(body.message, 'Ye joota available hai?');
    assert.equal(body.store_id, 'store-123');
    assert.equal(body.customer_number, '923001234567');
    assert.equal(body.whatsapp_message_id, 'msg-image-001');
    assert.equal(body.vision_description, 'A black athletic-style running shoe');
    assert.equal(body.vision_text_ocr, 'NIKE');
    assert.deepEqual(body.vision_attributes, ['black', 'athletic', 'shoe', 'sneaker']);
    assert.equal(body.vision_confidence, 0.92);
    assert.equal(body.original_caption, 'Ye joota available hai?');

    assert.equal(calls.sendText.length, 1);
    assert.equal(calls.sendText[0].text, 'We have the Black Runner in stock!');
  } finally {
    cleanup();
  }
});

test('image WITHOUT caption: still downloads, analyzes, and forwards a fallback message', async () => {
  const { webhookHandler, calls, cleanup } = setupMocks();
  try {
    await webhookHandler.handleMessagesUpsert(makeImagePayload()); // no caption

    assert.equal(calls.downloadMedia.length, 1);
    assert.equal(calls.analyzeImage.length, 1);
    assert.equal(calls.analyzeImage[0].caption, '');

    assert.equal(calls.backendPost.length, 1);
    const body = calls.backendPost[0].data;
    assert.equal(body.message_type, 'image');
    assert.equal(body.message, 'Customer sent a product image.');
    assert.equal(body.original_caption, '');
    // Vision context still forwarded.
    assert.equal(body.vision_description, 'A black athletic-style running shoe');
    assert.equal(calls.sendText.length, 1);
  } finally {
    cleanup();
  }
});

test('image: download failure sends honest fallback and no catalog guess', async () => {
  const { webhookHandler, mockEvolutionClient, calls, cleanup } = setupMocks();
  mockEvolutionClient.downloadMediaMessage = async () => { throw new Error('Network error'); };
  try {
    await webhookHandler.handleMessagesUpsert(makeImagePayload({ caption: 'shoe' }));

    assert.equal(calls.analyzeImage.length, 0);
    assert.equal(calls.backendPost.length, 0);
    assert.equal(calls.sendText.length, 1);
    assert.ok(calls.sendText[0].text.includes("couldn't read that image"));
  } finally {
    cleanup();
  }
});

test('image: non-image MIME sends fallback and never calls vision', async () => {
  const { webhookHandler, mockEvolutionClient, calls, cleanup } = setupMocks();
  mockEvolutionClient.downloadMediaMessage = async () => ({
    buffer: Buffer.from('data'),
    mimeType: 'application/pdf',
    fileName: 'media_x.pdf',
  });
  try {
    await webhookHandler.handleMessagesUpsert(makeImagePayload({ caption: 'x' }));

    assert.equal(calls.analyzeImage.length, 0);
    assert.equal(calls.backendPost.length, 0);
    assert.equal(calls.sendText.length, 1);
    assert.ok(calls.sendText[0].text.includes("couldn't read that image"));
  } finally {
    cleanup();
  }
});

test('image: vision failure (timeout/low-confidence/unsafe) sends fallback, no backend call', async () => {
  const { webhookHandler, mockVisionClient, calls, cleanup } = setupMocks();
  mockVisionClient.analyzeImage = async () => { throw new Error('Vision timeout exceeded'); };
  try {
    await webhookHandler.handleMessagesUpsert(makeImagePayload({ caption: 'shoe' }));

    assert.equal(calls.downloadMedia.length, 1);
    assert.equal(calls.backendPost.length, 0);
    assert.equal(calls.sendText.length, 1);
    assert.ok(calls.sendText[0].text.includes("couldn't read that image"));
  } finally {
    cleanup();
  }
});

test('image: duplicate message id processed only once', async () => {
  const { webhookHandler, calls, cleanup } = setupMocks();
  try {
    const payload = makeImagePayload({ caption: 'shoe' });
    await webhookHandler.handleMessagesUpsert(payload);
    await webhookHandler.handleMessagesUpsert(payload); // same key.id

    assert.equal(calls.downloadMedia.length, 1);
    assert.equal(calls.backendPost.length, 1);
  } finally {
    cleanup();
  }
});

test('sanitizeVisionResult: bounds lengths, clamps confidence, filters attributes', () => {
  const { webhookHandler, cleanup } = setupMocks();
  try {
    const out = webhookHandler.sanitizeVisionResult(
      {
        description: 'd'.repeat(5000),
        text_ocr: 'o'.repeat(5000),
        attributes: [
          'a'.repeat(200),
          '',
          '   ',
          42,
          null,
          ...Array.from({ length: 40 }, (_, i) => `attr${i}`),
        ],
        confidence: 5,
      },
      'c'.repeat(5000),
    );
    assert.equal(out.vision_description.length, 1000);
    assert.equal(out.vision_text_ocr.length, 1000);
    assert.ok(out.vision_attributes.length <= 20);
    assert.ok(out.vision_attributes.every((a) => a.length <= 60));
    // Empty / non-string attributes filtered out.
    assert.ok(out.vision_attributes.every((a) => typeof a === 'string' && a.trim()));
    assert.equal(out.vision_confidence, 1); // clamped to [0,1]
    assert.equal(out.original_caption.length, 1000);
  } finally {
    cleanup();
  }
});

test('sanitizeVisionResult: invalid confidence becomes 0', () => {
  const { webhookHandler, cleanup } = setupMocks();
  try {
    const out = webhookHandler.sanitizeVisionResult({ confidence: 'not-a-number' }, '');
    assert.equal(out.vision_confidence, 0);
    assert.deepEqual(out.vision_attributes, []);
    assert.equal(out.vision_description, '');
  } finally {
    cleanup();
  }
});
