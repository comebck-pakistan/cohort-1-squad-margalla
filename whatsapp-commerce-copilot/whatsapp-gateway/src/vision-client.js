const { GoogleGenAI } = require('@google/genai');
const config = require('./config');
const { createLogger, format, transports } = require('winston');
// image-size v1 exported the function directly; v2 exposes it as a named
// `imageSize` export. Resolve either shape so real images are measured
// correctly at runtime (test mocks provide the bare function).
const _imageSizeModule = require('image-size');
const sizeOf = typeof _imageSizeModule === 'function'
  ? _imageSizeModule
  : _imageSizeModule.imageSize;

const logger = createLogger({
  level: 'info',
  format: format.combine(format.timestamp(), format.json()),
  transports: [new transports.Console()],
});

const ALLOWED_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

/**
 * Validates and analyzes an image using Gemini.
 * @param {object} params
 * @param {Buffer} params.buffer
 * @param {string} params.mimeType
 * @param {string} params.fileName
 * @param {string} params.caption
 * @returns {Promise<object>} - Structured JSON output
 */
async function analyzeImage({ buffer, mimeType, fileName, caption }) {
  if (buffer.length > config.maxImageBytes) {
    logger.warn({ msg: 'Image too large', fileName, bytes: buffer.length, limit: config.maxImageBytes });
    throw new Error(`Image size exceeds limit of ${config.maxImageBytes} bytes`);
  }

  let dimensions;
  try {
    dimensions = sizeOf(buffer);
  } catch (err) {
    logger.warn({ msg: 'Malformed image or cannot read dimensions', fileName, error: err.message });
    throw new Error('Malformed or unsupported image format');
  }

  // Derive actual MIME from the file signature
  const actualMimeType = dimensions.type ? `image/${dimensions.type}` : mimeType;
  
  if (!ALLOWED_MIME_TYPES.includes(actualMimeType)) {
    logger.warn({ msg: 'Unsupported image MIME type', fileName, mimeType: actualMimeType });
    throw new Error('Unsupported image format');
  }

  const pixels = dimensions.width * dimensions.height;
  if (pixels > config.maxImagePixels) {
    logger.warn({ msg: 'Image dimensions too large', fileName, pixels, limit: config.maxImagePixels });
    throw new Error('Image dimensions exceed maximum allowed pixels');
  }

  const ai = new GoogleGenAI({ apiKey: config.geminiApiKey });

  // Convert buffer to base64
  const base64Image = buffer.toString('base64');

  const promptText = `
Analyze this image.
Caption provided by user: "${caption || ''}"
Provide a JSON response with the following fields:
- description: A concise description of the image.
- text_ocr: Any visible text found in the image.
- attributes: An array of probable product attributes (e.g. colors, style, category).
- confidence: A number between 0 and 1 indicating how confident you are.
- safety_status: 'safe' if it is appropriate, 'unsafe' if it contains explicit or harmful content, or 'unsupported' if it's not a product-related image.
`;

  const apiCallPromise = ai.models.generateContent({
    model: config.visionModel,
    contents: [
      {
        role: 'user',
        parts: [
          {
            inlineData: {
              mimeType: actualMimeType,
              data: base64Image,
            },
          },
          { text: promptText },
        ],
      },
    ],
    config: {
      responseMimeType: 'application/json',
      responseSchema: {
        type: 'object',
        properties: {
          description: { type: 'string' },
          text_ocr: { type: 'string' },
          attributes: { type: 'array', items: { type: 'string' } },
          confidence: { type: 'number' },
          safety_status: { type: 'string' }
        },
        required: ['description', 'text_ocr', 'attributes', 'confidence', 'safety_status']
      },
    }
  });

  let timeoutId;
  const timeoutPromise = new Promise((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error(`Vision timeout exceeded (${config.visionTimeoutMs}ms)`)), config.visionTimeoutMs);
  });

  try {
    const response = await Promise.race([apiCallPromise, timeoutPromise]);
    
    if (!response || !response.text) {
      throw new Error('Vision failed: returned empty response');
    }

    const result = JSON.parse(response.text);

    if (result.safety_status !== 'safe') {
      logger.warn({ msg: 'Vision rejected image for safety/unsupported', fileName, status: result.safety_status });
      throw new Error('Image rejected due to safety or unsupported content');
    }

    if (result.confidence < 0.4) {
      logger.warn({ msg: 'Vision confidence too low', fileName, confidence: result.confidence });
      throw new Error('Image analysis confidence too low');
    }

    logger.info({
      msg: 'Vision analysis complete',
      fileName,
      mimeType: actualMimeType,
      confidence: result.confidence
    });

    return result;
  } finally {
    clearTimeout(timeoutId);
  }
}

module.exports = { analyzeImage };
