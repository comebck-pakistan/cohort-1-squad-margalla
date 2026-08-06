const { describe, it, mock, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert');

// Mock config
require.cache[require.resolve('../src/config')] = {
  id: require.resolve('../src/config'),
  filename: require.resolve('../src/config'),
  loaded: true,
  exports: {
    geminiApiKey: 'test-api-key',
    transcriptionModel: 'gemini-2.5-flash',
    maxAudioBytes: 100,
    transcriptionTimeoutMs: 100
  }
};

// Mock winston
require.cache[require.resolve('winston')] = {
  id: require.resolve('winston'),
  filename: require.resolve('winston'),
  loaded: true,
  exports: {
    createLogger: () => ({
      info: () => {},
      warn: () => {},
      error: () => {}
    }),
    format: { combine: () => {}, timestamp: () => {}, json: () => {} },
    transports: { Console: class {} }
  }
};

// Mock @google/genai
const generateContentMock = mock.fn();
require.cache[require.resolve('@google/genai')] = {
  id: require.resolve('@google/genai'),
  filename: require.resolve('@google/genai'),
  loaded: true,
  exports: {
    GoogleGenAI: class {
      constructor() {
        this.models = {
          generateContent: generateContentMock
        };
      }
    }
  }
};

const { transcribeAudio } = require('../src/transcription-client');

describe('transcription-client', () => {
  beforeEach(() => {
    generateContentMock.mock.resetCalls();
  });

  it('successful transcription clears the timeout', async () => {
    generateContentMock.mock.mockImplementationOnce(() => Promise.resolve({ text: ' hello ' }));
    
    const result = await transcribeAudio({
      buffer: Buffer.from('abc'),
      mimeType: 'audio/ogg',
      fileName: 'test.ogg'
    });
    
    assert.strictEqual(result, 'hello');
  });

  it('rejected Gemini request clears the timeout', async () => {
    generateContentMock.mock.mockImplementationOnce(() => Promise.reject(new Error('API Error')));
    
    await assert.rejects(
      transcribeAudio({
        buffer: Buffer.from('abc'),
        mimeType: 'audio/ogg',
        fileName: 'test.ogg'
      }),
      /API Error/
    );
  });

  it('hanging request produces the configured timeout error', async () => {
    generateContentMock.mock.mockImplementationOnce(() => new Promise(resolve => setTimeout(resolve, 500)));
    
    await assert.rejects(
      transcribeAudio({
        buffer: Buffer.from('abc'),
        mimeType: 'audio/ogg',
        fileName: 'test.ogg'
      }),
      /Transcription timeout exceeded/
    );
  });

  it('empty response returns an empty transcript safely', async () => {
    generateContentMock.mock.mockImplementationOnce(() => Promise.resolve({}));
    
    const result = await transcribeAudio({
      buffer: Buffer.from('abc'),
      mimeType: 'audio/ogg',
      fileName: 'test.ogg'
    });
    
    assert.strictEqual(result, '');
  });

  it('unsupported MIME types are rejected before calling Gemini', async () => {
    await assert.rejects(
      transcribeAudio({
        buffer: Buffer.from('abc'),
        mimeType: 'video/mp4',
        fileName: 'test.mp4'
      }),
      /Unsupported MIME type/
    );
    assert.strictEqual(generateContentMock.mock.calls.length, 0);
  });

  it('oversized buffers are rejected before calling Gemini', async () => {
    await assert.rejects(
      transcribeAudio({
        buffer: Buffer.alloc(200),
        mimeType: 'audio/ogg',
        fileName: 'test.ogg'
      }),
      /Audio too large/
    );
    assert.strictEqual(generateContentMock.mock.calls.length, 0);
  });
});
