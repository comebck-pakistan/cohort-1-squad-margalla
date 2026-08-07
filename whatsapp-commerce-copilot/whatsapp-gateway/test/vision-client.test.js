const test = require('node:test');
const assert = require('node:assert/strict');
const { mock } = require('node:test');

function setupMocks() {
  delete require.cache[require.resolve('../src/vision-client')];
  delete require.cache[require.resolve('../src/config')];
  delete require.cache[require.resolve('@google/genai')];
  delete require.cache[require.resolve('image-size')];

  const mockConfig = {
    visionModel: 'gemini-1.5-flash',
    maxImageBytes: 1000,
    maxImagePixels: 1000000,
    visionTimeoutMs: 1000,
    geminiApiKey: 'test',
  };
  require.cache[require.resolve('../src/config')] = {
    id: require.resolve('../src/config'),
    filename: require.resolve('../src/config'),
    loaded: true,
    exports: mockConfig,
  };

  const generateContentMock = mock.fn(async () => {
    return {
      text: JSON.stringify({
        description: 'A test image',
        text_ocr: 'hello',
        attributes: ['test'],
        confidence: 0.9,
        safety_status: 'safe'
      })
    };
  });

  const GoogleGenAI = class {
    constructor() {
      this.models = { generateContent: generateContentMock };
    }
  };
  require.cache[require.resolve('@google/genai')] = {
    id: require.resolve('@google/genai'),
    filename: require.resolve('@google/genai'),
    loaded: true,
    exports: { GoogleGenAI },
  };

  const sizeOfMock = mock.fn(() => ({ width: 800, height: 600, type: 'jpeg' }));
  require.cache[require.resolve('image-size')] = {
    id: require.resolve('image-size'),
    filename: require.resolve('image-size'),
    loaded: true,
    exports: sizeOfMock,
  };

  const visionClient = require('../src/vision-client');

  return { visionClient, generateContentMock, sizeOfMock, mockConfig, cleanup: () => {
    delete require.cache[require.resolve('../src/vision-client')];
    delete require.cache[require.resolve('../src/config')];
    delete require.cache[require.resolve('@google/genai')];
    delete require.cache[require.resolve('image-size')];
  }};
}

test('analyzeImage: succeeds with valid image', async () => {
  const { visionClient, generateContentMock, sizeOfMock, cleanup } = setupMocks();
  try {
    const buffer = Buffer.alloc(500);
    const result = await visionClient.analyzeImage({
      buffer,
      mimeType: 'image/jpeg',
      fileName: 'test.jpg',
      caption: 'Look at this'
    });

    assert.equal(result.description, 'A test image');
    assert.equal(generateContentMock.mock.calls.length, 1);
    assert.equal(sizeOfMock.mock.calls.length, 1);
  } finally {
    cleanup();
  }
});

test('analyzeImage: rejects oversized buffer', async () => {
  const { visionClient, generateContentMock, cleanup } = setupMocks();
  try {
    const buffer = Buffer.alloc(2000); // Exceeds 1000
    await assert.rejects(
      visionClient.analyzeImage({ buffer, mimeType: 'image/jpeg', fileName: 'test.jpg' }),
      /Image size exceeds limit/
    );
    assert.equal(generateContentMock.mock.calls.length, 0);
  } finally {
    cleanup();
  }
});

test('analyzeImage: rejects malformed image (sizeOf throws)', async () => {
  const { visionClient, sizeOfMock, cleanup } = setupMocks();
  sizeOfMock.mock.mockImplementation(() => { throw new Error('invalid'); });
  try {
    const buffer = Buffer.alloc(500);
    await assert.rejects(
      visionClient.analyzeImage({ buffer, mimeType: 'image/jpeg', fileName: 'test.jpg' }),
      /Malformed or unsupported/
    );
  } finally {
    cleanup();
  }
});

test('analyzeImage: rejects unsupported MIME type', async () => {
  const { visionClient, sizeOfMock, cleanup } = setupMocks();
  sizeOfMock.mock.mockImplementation(() => ({ width: 800, height: 600, type: 'gif' }));
  try {
    const buffer = Buffer.alloc(500);
    await assert.rejects(
      visionClient.analyzeImage({ buffer, mimeType: 'image/gif', fileName: 'test.gif' }),
      /Unsupported image format/
    );
  } finally {
    cleanup();
  }
});

test('analyzeImage: rejects oversized dimensions', async () => {
  const { visionClient, sizeOfMock, cleanup } = setupMocks();
  sizeOfMock.mock.mockImplementation(() => ({ width: 2000, height: 2000, type: 'jpeg' })); // 4,000,000 > 1,000,000
  try {
    const buffer = Buffer.alloc(500);
    await assert.rejects(
      visionClient.analyzeImage({ buffer, mimeType: 'image/jpeg', fileName: 'test.jpg' }),
      /Image dimensions exceed maximum/
    );
  } finally {
    cleanup();
  }
});

test('analyzeImage: rejects low confidence', async () => {
  const { visionClient, generateContentMock, cleanup } = setupMocks();
  generateContentMock.mock.mockImplementation(async () => ({
    text: JSON.stringify({ description: 'A test image', text_ocr: '', attributes: [], confidence: 0.2, safety_status: 'safe' })
  }));
  try {
    const buffer = Buffer.alloc(500);
    await assert.rejects(
      visionClient.analyzeImage({ buffer, mimeType: 'image/jpeg', fileName: 'test.jpg' }),
      /confidence too low/
    );
  } finally {
    cleanup();
  }
});

test('analyzeImage: rejects unsafe content', async () => {
  const { visionClient, generateContentMock, cleanup } = setupMocks();
  generateContentMock.mock.mockImplementation(async () => ({
    text: JSON.stringify({ description: 'A test image', text_ocr: '', attributes: [], confidence: 0.9, safety_status: 'unsafe' })
  }));
  try {
    const buffer = Buffer.alloc(500);
    await assert.rejects(
      visionClient.analyzeImage({ buffer, mimeType: 'image/jpeg', fileName: 'test.jpg' }),
      /safety or unsupported/
    );
  } finally {
    cleanup();
  }
});

test('analyzeImage: throws on timeout', async () => {
  const { visionClient, generateContentMock, mockConfig, cleanup } = setupMocks();
  mockConfig.visionTimeoutMs = 100;
  generateContentMock.mock.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 500)));
  try {
    const buffer = Buffer.alloc(500);
    await assert.rejects(
      visionClient.analyzeImage({ buffer, mimeType: 'image/jpeg', fileName: 'test.jpg' }),
      /Vision timeout exceeded/
    );
  } finally {
    cleanup();
  }
});
