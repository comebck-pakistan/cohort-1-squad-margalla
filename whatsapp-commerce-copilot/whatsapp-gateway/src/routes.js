/**
 * WhatsApp Gateway Express Routes
 * Internal API for backend communication.
 * Same route shapes as the original gateway — backend doesn't need to change.
 */
const express = require('express');
const config = require('./config');
const evolutionClient = require('./evolution-client');
const { webhookHandler, getCachedQR, mapConnectionState } = require('./webhook-handler');

function createRoutes() {
  const router = express.Router();

  // Auth middleware for internal routes
  const authMiddleware = (req, res, next) => {
    const token = req.headers['x-internal-token'];
    if (token !== config.internalToken) {
      return res.status(401).json({ error: 'Unauthorized' });
    }
    next();
  };

  // Health check — includes Evolution API reachability
  router.get('/health', async (req, res) => {
    const evolutionHealthy = await evolutionClient.isHealthy();
    res.json({
      status: evolutionHealthy ? 'ok' : 'degraded',
      service: 'whatsapp-gateway',
      transport: 'evolution-api',
      transportVersion: config.evolutionApiVersion,
      evolutionApiReachable: evolutionHealthy,
    });
  });

  // Connect a store (create/connect WhatsApp instance via Evolution API)
  router.post('/sessions/:storeId/connect', authMiddleware, async (req, res) => {
    try {
      const { storeId } = req.params;

      // Check if instance already exists
      const existing = await evolutionClient.fetchInstance(storeId);

      if (existing) {
        // Instance exists — try to connect (generate new QR)
        try {
          const connectResult = await evolutionClient.connectInstance(storeId);
          // Extract QR from connect response if available
          const qrBase64 = connectResult?.base64 || connectResult?.qrcode?.base64 || null;
          return res.json({
            status: 'initializing',
            storeId,
            qr_code: qrBase64,
          });
        } catch (err) {
          // If connect fails, the instance might be in a bad state — delete and recreate
          await evolutionClient.deleteInstance(storeId);
        }
      }

      // Create new instance
      const result = await evolutionClient.createInstance(storeId);

      // Evolution API may return QR code immediately in the create response
      const qrBase64 = result?.qrcode?.base64 || null;

      res.json({
        status: 'initializing',
        storeId,
        qr_code: qrBase64,
      });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });

  // Get session status
  router.get('/sessions/:storeId/status', async (req, res) => {
    const { storeId } = req.params;

    try {
      const stateResult = await evolutionClient.getConnectionState(storeId);
      const evolutionState = stateResult?.instance?.state || stateResult?.state || 'close';
      const mappedStatus = mapConnectionState(evolutionState);

      res.json({
        storeId,
        status: mappedStatus,
        qrCode: getCachedQR(storeId),
        phoneNumber: null, // Evolution API doesn't expose this in connectionState
      });
    } catch (err) {
      // Instance doesn't exist
      res.json({
        storeId,
        status: 'disconnected',
        qrCode: null,
        phoneNumber: null,
      });
    }
  });

  // Get QR code
  router.get('/sessions/:storeId/qr', (req, res) => {
    const { storeId } = req.params;
    const qr = getCachedQR(storeId);
    if (!qr) {
      return res.status(404).json({ error: 'QR not available', status: 'waiting' });
    }
    res.json({ qr_code: qr, storeId });
  });

  // Disconnect
  router.delete('/sessions/:storeId', authMiddleware, async (req, res) => {
    try {
      const { storeId } = req.params;
      await evolutionClient.deleteInstance(storeId);
      res.json({ status: 'disconnected', storeId });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });

  // Send message (called by backend)
  router.post('/send', authMiddleware, async (req, res) => {
    try {
      const { store_id, customer_number, message } = req.body;
      await evolutionClient.sendText(store_id, customer_number, message);
      res.json({ status: 'sent' });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });

  // Evolution API webhook receiver
  router.post('/webhook/evolution', webhookHandler);

  return router;
}

module.exports = createRoutes;
