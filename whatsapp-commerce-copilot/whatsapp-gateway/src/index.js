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
app.use(express.json({ limit: '1mb' }));

// Mount routes
app.use('/', createRoutes());

// Start server
app.listen(config.port, () => {
  logger.info({
    msg: 'WhatsApp Gateway started (Evolution API adapter)',
    port: config.port,
    backendUrl: config.backendUrl,
    evolutionApiUrl: config.evolutionApiUrl,
    evolutionApiVersion: config.evolutionApiVersion,
    webhookUrl: config.evolutionWebhookUrl,
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
