/**
 * Multi-image gallery replies.
 *
 * A colour's designs arrive as several numbered images. The customer answers
 * with a number, so the images MUST arrive in the order the backend numbered
 * them — that is what these tests pin down, along with the Evolution payload
 * fields without which sendMedia silently fails.
 */
const test = require('node:test');
const assert = require('node:assert/strict');

function stubModule(path, exports) {
  const resolved = require.resolve(path);
  require.cache[resolved] = { id: resolved, filename: resolved, loaded: true, exports };
}

/**
 * Load webhook-handler with the backend and the WhatsApp client stubbed out.
 * `sendLog` records every outbound call in the order it COMPLETED, and each
 * stub yields to the event loop so a parallel send would interleave visibly.
 */
function setup(backendData, { failMediaAt = null } = {}) {
  delete require.cache[require.resolve('../src/webhook-handler')];
  delete require.cache[require.resolve('../src/evolution-client')];
  delete require.cache[require.resolve('../src/config')];

  stubModule('../src/config', {
    port: 3001,
    backendUrl: 'http://localhost:8000',
    internalToken: 'test-token',
    evolutionApiUrl: 'http://localhost:8080',
    evolutionApiKey: 'test-key',
    maxInboundAgeSeconds: 300,
    sendDelayMs: 0,
  });

  const sendLog = [];
  let inFlight = 0;
  let sawOverlap = false;
  let mediaCount = 0;

  const settle = async (fn) => {
    inFlight += 1;
    if (inFlight > 1) sawOverlap = true;
    await new Promise((r) => setImmediate(r));
    try {
      return fn();
    } finally {
      inFlight -= 1;
    }
  };

  stubModule('../src/evolution-client', {
    sendText: async (storeId, to, text) =>
      settle(() => { sendLog.push({ kind: 'text', text }); return {}; }),
    sendMedia: async (storeId, to, url, caption) =>
      settle(() => {
        mediaCount += 1;
        if (failMediaAt === mediaCount) throw new Error('evolution 400');
        sendLog.push({ kind: 'media', url, caption });
        return {};
      }),
  });

  // webhook-handler holds the same axios module object, so patching .post here
  // intercepts its backend call without touching the module graph.
  const axios = require('axios');
  const originalPost = axios.post;
  axios.post = async (url, data) => {
    if (url.includes('/internal/whatsapp/messages')) {
      return { data: { store_id: data.store_id, ...backendData } };
    }
    throw new Error(`unexpected POST ${url}`);
  };

  const handler = require('../src/webhook-handler');
  const restore = () => { axios.post = originalPost; };
  return { handler, sendLog, restore, overlapped: () => sawOverlap };
}

const GALLERY = {
  message: '2 designs available in Black Cotton:',
  media_footer: "Reply with a number to select a design, 'Back' for colors.",
  intent: 'color_products',
  confidence: 1.0,
  media_items: [
    { product_id: 'p1', image_url: '/uploads/black-1.jpg', caption: '1. Black Cotton Kurta — Rs. 2,500' },
    { product_id: 'p2', image_url: '/uploads/black-2.jpg', caption: '2. Black Cotton Suit — Rs. 3,200' },
    { product_id: 'p3', image_url: '/uploads/black-3.jpg', caption: '3. Black Cotton Frock — Rs. 4,000' },
  ],
};

test('gallery: header, every image in order, then the reply prompt', async () => {
  const { handler, sendLog, restore } = setup(GALLERY);
  try {
    await handler.forwardAndReply('store-1', '923001234567', 'Black', 'text', 'msg-1');
  } finally {
    restore();
  }

  assert.deepEqual(sendLog.map((s) => s.kind),
    ['text', 'media', 'media', 'media', 'text']);
  assert.equal(sendLog[0].text, GALLERY.message);
  assert.deepEqual(sendLog.slice(1, 4).map((s) => s.caption),
    GALLERY.media_items.map((i) => i.caption));
  assert.deepEqual(sendLog.slice(1, 4).map((s) => s.url),
    GALLERY.media_items.map((i) => i.image_url));
  assert.equal(sendLog[4].text, GALLERY.media_footer);
});

test('gallery: sends are sequential, never raced', async () => {
  const { handler, restore, overlapped } = setup(GALLERY);
  try {
    await handler.forwardAndReply('store-1', '923001234567', 'Black', 'text', 'msg-2');
  } finally {
    restore();
  }
  // Promise.all would put two sends in flight at once and scramble the numbering.
  assert.equal(overlapped(), false);
});

test('gallery: a failed image falls back to the numbered text list', async () => {
  const { handler, sendLog, restore } = setup(GALLERY, { failMediaAt: 2 });
  try {
    await handler.forwardAndReply('store-1', '923001234567', 'Black', 'text', 'msg-3');
  } finally {
    restore();
  }
  const texts = sendLog.filter((s) => s.kind === 'text').map((s) => s.text);
  const fallback = texts[texts.length - 1];
  // Customer still gets every numbered design and the prompt — never silence.
  for (const item of GALLERY.media_items) {
    assert.ok(fallback.includes(item.caption), `missing ${item.caption}`);
  }
  assert.ok(fallback.includes(GALLERY.media_footer));
  // The header already went out on its own; it is not repeated.
  assert.ok(!fallback.includes(GALLERY.message));
});

test('single-image replies still use the plain sendMedia path', async () => {
  const { handler, sendLog, restore } = setup({
    message: 'Black Cotton Kurta — Rs. 2,500',
    image_url: '/uploads/black-1.jpg',
    intent: 'product_search',
    confidence: 1.0,
  });
  try {
    await handler.forwardAndReply('store-1', '923001234567', '1', 'text', 'msg-4');
  } finally {
    restore();
  }
  assert.deepEqual(sendLog.map((s) => s.kind), ['media']);
  assert.equal(sendLog[0].caption, 'Black Cotton Kurta — Rs. 2,500');
});

test('text-only replies are unaffected by the gallery branch', async () => {
  const { handler, sendLog, restore } = setup({
    message: 'Available sizes: S, M, L',
    media_items: [],
    intent: 'order_request',
    confidence: 1.0,
  });
  try {
    await handler.forwardAndReply('store-1', '923001234567', 'Order', 'text', 'msg-5');
  } finally {
    restore();
  }
  assert.deepEqual(sendLog.map((s) => s.kind), ['text']);
});

test('sendMedia posts the mimetype and fileName Evolution requires', async () => {
  delete require.cache[require.resolve('../src/evolution-client')];
  delete require.cache[require.resolve('../src/config')];
  stubModule('../src/config', {
    evolutionApiUrl: 'http://localhost:8080',
    evolutionApiKey: 'test-key',
    backendUrl: 'http://backend:8000',
    sendDelayMs: 0,
  });

  const axios = require('axios');
  const originalCreate = axios.create;
  const posts = [];
  axios.create = () => ({
    post: async (url, payload) => { posts.push({ url, payload }); return { data: {} }; },
    delete: async () => ({ data: {} }),
    get: async () => ({ data: {} }),
  });
  try {
    const client = require('../src/evolution-client');
    await client.sendMedia('store-1', '923001234567', '/uploads/black-1.jpg', '1. Black Cotton Kurta');
  } finally {
    axios.create = originalCreate;
    delete require.cache[require.resolve('../src/evolution-client')];
  }

  assert.equal(posts.length, 1);
  const { payload } = posts[0];
  assert.equal(payload.mediatype, 'image');
  assert.equal(payload.mimetype, 'image/jpeg');
  assert.equal(payload.fileName, 'product.jpg');
  assert.equal(payload.caption, '1. Black Cotton Kurta');
  // relative catalogue paths are resolved against the backend so Evolution can fetch them
  assert.equal(payload.media, 'http://backend:8000/uploads/black-1.jpg');
});
