/**
 * WhatsApp Gateway — Entry Point
 * Evolution API adapter service.
 * Transport-only Node.js service — zero business logic.
 * All catalog, pricing, inventory, orders are handled by the Python backend.
 */
const express = require('express');
const config = require('./config');
const createRoutes = require('./routes');
const { createLogger, format, transports } = require('winston');

const logger = createLogger({
  level: 'info',
  format: format.combine(format.timestamp(), format.json()),
  transports: [new transports.Console()],
});

const app = express();

// 10 MB safety net. Primary fix for oversized webhooks is base64:false in
// webhook config — but if a large payload still arrives (e.g. during config
// transition), we accept it rather than triggering an Evolution retry storm.
app.use(express.json({ limit: '10mb' }));

// Mount routes
app.use('/', createRoutes());

// Graceful handler for payloads that still exceed the limit.
// Returns 200 so Evolution does NOT retry. Logs safe metadata only.
app.use((err, req, res, _next) => {
  if (err.type === 'entity.too.large') {
    const contentLength = req.headers['content-length'] || 'unknown';
    logger.warn({
      msg: 'Oversized webhook payload rejected gracefully',
      contentLength,
      path: req.path,
    });
    return res.status(200).json({ status: 'rejected', reason: 'payload_too_large' });
  }
  // Other Express errors
  logger.error({ msg: 'Unhandled Express error', error: err.message });
  res.status(500).json({ error: 'Internal server error' });
});

// Start server
app.listen(config.port, () => {
  logger.info({
    msg: 'WhatsApp Gateway started (Evolution API adapter)',
    port: config.port,
    backendUrl: config.backendUrl,
    evolutionApiUrl: config.evolutionApiUrl,
    evolutionApiVersion: config.evolutionApiVersion,
    webhookUrl: config.evolutionWebhookUrl,
    sendDelayMs: config.sendDelayMs,
    webhookBase64: config.webhookBase64,
  });
});

// Graceful shutdown
process.on('SIGINT', async () => {
  logger.info({ msg: 'Shutting down gateway...' });
  process.exit(0);
});

process.on('SIGTERM', async () => {
  logger.info({ msg: 'Shutting down gateway...' });
  process.exit(0);
});
