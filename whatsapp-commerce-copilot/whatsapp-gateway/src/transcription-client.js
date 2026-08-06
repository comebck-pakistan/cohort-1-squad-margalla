/**
 * Audio Transcription Client
 * Uses Google Gemini API to convert voice messages to text.
 * Reuses the same GEMINI_API_KEY used by the backend for conversational AI.
 */
const { GoogleGenAI } = require('@google/genai');
const config = require('./config');
const { createLogger, format, transports } = require('winston');

const logger = createLogger({
  level: 'info',
  format: format.combine(format.timestamp(), format.json()),
  transports: [new transports.Console()],
});

/**
 * Transcribe an audio buffer to text using Gemini's multimodal API.
 * Sends base64 audio inline — no file upload or temp files needed.
 * Does NOT translate — preserves original language (Urdu, English, Hindi, Roman Urdu, code-switched).
 *
 * @param {object} params
 * @param {Buffer} params.buffer — audio data
 * @param {string} params.mimeType — e.g. "audio/ogg"
 * @param {string} params.fileName — e.g. "voice_abc123.ogg" (for logging only)
 * @returns {Promise<string>} trimmed transcript text
 */
async function transcribeAudio({ buffer, mimeType, fileName }) {
  if (!config.geminiApiKey) {
    throw new Error('GEMINI_API_KEY not configured for voice transcription');
  }

  // Validate MIME type
  if (!mimeType || !mimeType.startsWith('audio/')) {
    throw new Error(`Unsupported MIME type for transcription: ${mimeType}`);
  }

  // Validate size
  if (buffer.length > config.maxAudioBytes) {
    throw new Error(
      `Audio too large: ${buffer.length} bytes exceeds limit of ${config.maxAudioBytes} bytes`
    );
  }

  const ai = new GoogleGenAI({ apiKey: config.geminiApiKey });

  // Never log audio content
  logger.info({
    msg: 'Sending audio for transcription',
    fileName,
    mimeType,
    bytes: buffer.length,
    model: config.transcriptionModel,
  });

  const base64Audio = buffer.toString('base64');

  const response = await ai.models.generateContent({
    model: config.transcriptionModel,
    contents: [
      {
        role: 'user',
        parts: [
          {
            inlineData: {
              mimeType: mimeType,
              data: base64Audio,
            },
          },
          {
            text: 'Transcribe this audio faithfully. Output ONLY the transcript text, nothing else. Do not translate — preserve the original spoken language exactly as spoken, including Urdu, English, Hindi, Roman Urdu, or code-switched speech.',
          },
        ],
      },
    ],
  });

  const transcript = (response.text || '').trim();

  logger.info({
    msg: 'Transcription complete',
    fileName,
    transcriptLength: transcript.length,
  });

  return transcript;
}

module.exports = { transcribeAudio };
