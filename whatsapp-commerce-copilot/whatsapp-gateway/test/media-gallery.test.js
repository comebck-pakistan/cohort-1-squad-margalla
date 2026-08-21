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

  // Capture the gateway's own logging: a swallowed media error is the exact
  // failure mode these tests exist to prevent, so the log line is part of the
  // contract, not incidental output. The handler builds its logger at require
  // time, so winston is stubbed before it is loaded.
  const logged = [];
  const winston = require('winston');
  const realWinston = require.cache[require.resolve('winston')].exports;
  require.cache[require.resolve('winston')].exports = {
    ...realWinston,
    createLogger: () => ({
      info: () => {},
      warn: () => {},
      error: (o) => { logged.push(o); },
      debug: () => {},
    }),
  };

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
  const restore = () => {
    axios.post = originalPost;
    require.cache[require.resolve('winston')].exports = realWinston;
  };
  return { handler, sendLog, restore, overlapped: () => sawOverlap, logged };
}

const GALLERY = {
  message: '2 designs available in Black Cotton:',
  media_footer: "Reply with a number to select a design, 'Back' for colors.",
  intent: 'color_products',
  confidence: 1.0,
  // Shaped exactly as the backend emits it: absolute URL, the ids needed to map
  // a numbered reply back to a row, and the mandated multi-line caption.
  media_items: [
    { product_id: 'p1', variant_id: 'v1', selection_number: 1,
      image_url: 'http://backend:8000/uploads/black-1.jpg',
      caption: '1. Black Cotton Kurta\nCategory: Cotton\nColour: Black\nPrice: PKR 2,500' },
    { product_id: 'p2', variant_id: 'v2', selection_number: 2,
      image_url: 'http://backend:8000/uploads/black-2.jpg',
      caption: '2. Black Cotton Suit\nCategory: Cotton\nColour: Black\nPrice: PKR 3,200' },
    { product_id: 'p3', variant_id: 'v3', selection_number: 3,
      image_url: 'http://backend:8000/uploads/black-3.jpg',
      caption: '3. Black Cotton Frock\nCategory: Cotton\nColour: Black\nPrice: PKR 4,000' },
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

test('gallery: one failed image does not cost the customer the others', async () => {
  const { handler, sendLog, restore } = setup(GALLERY, { failMediaAt: 1 });
  try {
    await handler.forwardAndReply('store-1', '923001234567', 'Black', 'text', 'msg-3');
  } finally {
    restore();
  }
  // Image 1 blew up; 2 and 3 must still arrive as pictures.
  const sentCaptions = sendLog.filter((s) => s.kind === 'media').map((s) => s.caption);
  assert.deepEqual(sentCaptions, [
    GALLERY.media_items[1].caption,
    GALLERY.media_items[2].caption,
  ]);
});

test('gallery: the design that could not be pictured still reaches the customer', async () => {
  const { handler, sendLog, restore } = setup(GALLERY, { failMediaAt: 2 });
  try {
    await handler.forwardAndReply('store-1', '923001234567', 'Black', 'text', 'msg-3b');
  } finally {
    restore();
  }
  const texts = sendLog.filter((s) => s.kind === 'text').map((s) => s.text);
  // Only the design that failed is repeated as text — the two that were
  // pictured are not sent twice.
  const missed = texts.find((t) => t.includes(GALLERY.media_items[1].caption));
  assert.ok(missed, 'the failed design was never mentioned');
  assert.ok(!missed.includes(GALLERY.media_items[0].caption));
  assert.ok(!missed.includes(GALLERY.media_items[2].caption));
  // The header already went out on its own; it is not repeated.
  assert.ok(!missed.includes(GALLERY.message));
});

test('gallery: the footer is sent exactly once, after everything else', async () => {
  const { handler, sendLog, restore } = setup(GALLERY, { failMediaAt: 2 });
  try {
    await handler.forwardAndReply('store-1', '923001234567', 'Black', 'text', 'msg-3c');
  } finally {
    restore();
  }
  const footers = sendLog.filter((s) => s.kind === 'text' && s.text === GALLERY.media_footer);
  assert.equal(footers.length, 1);
  assert.equal(sendLog[sendLog.length - 1].text, GALLERY.media_footer);
});

test('gallery: a media failure is logged with its real reason, never swallowed', async () => {
  const { handler, restore, logged } = setup(GALLERY, { failMediaAt: 2 });
  try {
    await handler.forwardAndReply('store-1', '923001234567', 'Black', 'text', 'msg-3d');
  } finally {
    restore();
  }
  const err = logged.find((l) => l.msg === 'Gallery image send failed');
  assert.ok(err, 'no error was logged for the failed image');
  assert.equal(err.error, 'evolution 400');
  assert.equal(err.productId, 'p2');
  assert.equal(err.selectionNumber, 2);
  // Diagnostics must never carry the customer's number.
  assert.ok(!JSON.stringify(logged).includes('923001234567'));
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

test('sendMedia declares the mimetype that matches the file, not always JPEG', async () => {
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
    post: async (url, payload) => { posts.push(payload); return { data: {} }; },
    delete: async () => ({ data: {} }),
    get: async () => ({ data: {} }),
  });
  try {
    const client = require('../src/evolution-client');
    // Uploads are normalised to JPEG, but a seller may point at a hosted PNG or
    // WebP — declaring those as image/jpeg makes WhatsApp drop the picture.
    await client.sendMedia('s', '92300', 'https://cdn.example/a.png', 'c');
    await client.sendMedia('s', '92300', 'https://cdn.example/b.webp', 'c');
    await client.sendMedia('s', '92300', 'https://cdn.example/c.jpg?v=2', 'c');
    await client.sendMedia('s', '92300', 'https://cdn.example/d', 'c');
  } finally {
    axios.create = originalCreate;
    delete require.cache[require.resolve('../src/evolution-client')];
  }

  assert.deepEqual(posts.map((p) => p.mimetype),
    ['image/png', 'image/webp', 'image/jpeg', 'image/jpeg']);
  assert.deepEqual(posts.map((p) => p.fileName),
    ['product.png', 'product.webp', 'product.jpg', 'product.jpg']);
  // An absolute URL is passed through untouched.
  assert.equal(posts[0].media, 'https://cdn.example/a.png');
});

test('a media failure never logs the customer\'s full number', async () => {
  delete require.cache[require.resolve('../src/evolution-client')];
  delete require.cache[require.resolve('../src/config')];
  stubModule('../src/config', {
    evolutionApiUrl: 'http://localhost:8080',
    evolutionApiKey: 'test-key',
    backendUrl: 'http://backend:8000',
    sendDelayMs: 0,
  });

  const logged = [];
  const winston = require('winston');
  const realWinston = require.cache[require.resolve('winston')].exports;
  require.cache[require.resolve('winston')].exports = {
    ...realWinston,
    createLogger: () => ({
      info: () => {}, warn: () => {}, debug: () => {},
      error: (o) => { logged.push(o); },
    }),
  };

  const axios = require('axios');
  const originalCreate = axios.create;
  axios.create = () => ({
    post: async () => { throw new Error('evolution 404'); },
    delete: async () => ({ data: {} }),
    get: async () => ({ data: {} }),
  });
  try {
    const client = require('../src/evolution-client');
    await assert.rejects(() =>
      client.sendMedia('s', '923001234567', '/uploads/a.jpg', 'c'));
  } finally {
    axios.create = originalCreate;
    require.cache[require.resolve('winston')].exports = realWinston;
    delete require.cache[require.resolve('../src/evolution-client')];
  }

  const dump = JSON.stringify(logged);
  assert.ok(!dump.includes('923001234567'), 'the full number reached the logs');
  assert.ok(dump.includes('9230XXXXXXX'), `expected a masked number, got ${dump}`);
});
