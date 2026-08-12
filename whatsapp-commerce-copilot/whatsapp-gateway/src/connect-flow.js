/**
 * Connection flow for a store's WhatsApp instance.
 *
 * Ordering is deliberate and load-bearing:
 *   1. Validate + normalize the phone number (if one was supplied).
 *      Invalid input returns 400 and NEVER touches any Evolution instance —
 *      it must not call fetchInstance, deleteInstance, connectInstance, or
 *      createInstance. This prevents destroying a working instance because the
 *      user typed a bad number in "phone" mode.
 *   2. Inspect the existing instance and its connection state.
 *   3. Never delete an already-open instance — return "already connected".
 *   4. Only then decide the safe action (recreate for pairing / connect for QR
 *      / create fresh).
 *
 * Pairing-code lifecycle:
 *   After Evolution returns a pairing code the Baileys socket frequently closes
 *   immediately with 428 / stream:error 515 / "Connection Closed".  The code
 *   returned belongs to a dead socket and must never be displayed.
 *
 *   This module validates the connection state after create, accepts
 *   "connecting" as valid, and treats immediate "close" as a failed attempt.
 *   It retries up to MAX_PAIRING_ATTEMPTS times with bounded deletion polling,
 *   then returns a truthful failure if all attempts are exhausted.
 *
 * Evolution errors are mapped to safe statuses via mapUpstreamError and never
 * leak raw upstream bodies, phone numbers, pairing codes, or stack traces.
 */
const { normalizePhoneNumber } = require('./phone');
const { mapUpstreamError } = require('./upstream-error');
const { createLogger, format, transports } = require('winston');

const logger = createLogger({
  level: 'info',
  format: format.combine(format.timestamp(), format.json()),
  transports: [new transports.Console()],
});

const INVALID_PHONE_RESPONSE = {
  status: 400,
  body: { error: 'invalid_phone_number', message: 'Enter a valid international phone number.' },
};

/** Maximum pairing code generation attempts before giving up. */
const MAX_PAIRING_ATTEMPTS = 3;

/** Maximum polls to confirm instance deletion before proceeding. */
const MAX_DELETE_POLLS = 5;

/** Milliseconds between deletion confirmation polls. */
const DELETE_POLL_INTERVAL_MS = 800;

/** Milliseconds to wait after code generation before checking connection state. */
const POST_CREATE_SETTLE_MS = 2000;

/**
 * Wait for an instance to be fully deleted using bounded polling.
 * Returns true if confirmed gone, false if still present after max polls.
 */
async function waitForDeletion(evolutionClient, storeId, maxPolls = MAX_DELETE_POLLS, pollIntervalMs = DELETE_POLL_INTERVAL_MS) {
  for (let i = 0; i < maxPolls; i++) {
    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
    const inst = await evolutionClient.fetchInstance(storeId);
    if (!inst) return true;
  }
  return false;
}

/**
 * Extract the connection state string from an Evolution API connectionState response.
 */
function extractState(stateResult) {
  return (stateResult && stateResult.instance && stateResult.instance.state)
    || (stateResult && stateResult.state)
    || 'close';
}

/**
 * Check if an error indicates a pairing-specific failure (428, 515, Connection Closed).
 */
function isPairingFailure(err) {
  if (!err) return false;
  const msg = String(err.message || '');
  const status = err.response?.status;
  return (
    status === 428
    || /515|Connection Closed|stream.error/i.test(msg)
    || /428|Precondition Required/i.test(msg)
  );
}

/**
 * @param {object} deps
 * @param {object} deps.evolutionClient — Evolution API client (injectable for tests)
 * @param {string} deps.storeId
 * @param {string} [deps.phoneNumber] — raw, user-entered (may be formatted)
 * @param {number} [deps.recreateDelayMs] — settle delay after delete before recreate
 * @param {number} [deps.maxAttempts] — override MAX_PAIRING_ATTEMPTS for tests
 * @returns {Promise<{ status: number, body: object }>}
 */
async function connectSession({
  evolutionClient,
  storeId,
  phoneNumber,
  recreateDelayMs = POST_CREATE_SETTLE_MS,
  maxAttempts = MAX_PAIRING_ATTEMPTS,
}) {
  // 1. Validate/normalize phone FIRST — before any instance inspection or mutation.
  let normalizedPhone = null;
  const hasPhone =
    phoneNumber !== undefined && phoneNumber !== null && String(phoneNumber).trim() !== '';
  if (hasPhone) {
    const result = normalizePhoneNumber(phoneNumber);
    if (!result.ok) {
      return INVALID_PHONE_RESPONSE;
    }
    normalizedPhone = result.digits;
  }

  try {
    // 2. Inspect existing instance.
    const existing = await evolutionClient.fetchInstance(storeId);

    if (existing) {
      // Determine the current connection state before deciding to mutate anything.
      let state = 'close';
      try {
        const st = await evolutionClient.getConnectionState(storeId);
        state = extractState(st);
      } catch {
        state = 'close';
      }

      // 3. Never destroy an open instance just because phone mode was selected.
      if (state === 'open') {
        return {
          status: 200,
          body: { status: 'connected', storeId, qr_code: null, pairing_code: null },
        };
      }

      if (normalizedPhone) {
        // Pairing path — delete stale instance, then create fresh below.
        await evolutionClient.deleteInstance(storeId);
        await waitForDeletion(evolutionClient, storeId);
      } else {
        // QR path — try to connect the existing instance (generate a new QR).
        try {
          const connectResult = await evolutionClient.connectInstance(storeId);
          const qrBase64 =
            (connectResult && connectResult.base64) ||
            (connectResult && connectResult.qrcode && connectResult.qrcode.base64) ||
            null;
          return {
            status: 200,
            body: { status: 'initializing', storeId, qr_code: qrBase64, pairing_code: null },
          };
        } catch {
          // Instance may be in a bad state — remove it and recreate below.
          await evolutionClient.deleteInstance(storeId);
          await waitForDeletion(evolutionClient, storeId);
        }
      }
    }

    // 4. Create instance — with bounded retry for pairing mode.
    if (normalizedPhone) {
      return await createWithPairingRetry(evolutionClient, storeId, normalizedPhone, recreateDelayMs, maxAttempts);
    }

    // QR mode — single create, no retry needed.
    const result = await evolutionClient.createInstance(storeId, null);
    const qrBase64 = (result && result.qrcode && result.qrcode.base64) || null;
    return {
      status: 200,
      body: { status: 'initializing', storeId, qr_code: qrBase64, pairing_code: null },
    };
  } catch (err) {
    return mapUpstreamError(err);
  }
}

/**
 * Attempt to create an instance with a phone number for pairing-code flow.
 * Validates the connection state after each attempt. Retries up to maxAttempts
 * times if the socket dies immediately (428/515/"Connection Closed").
 *
 * Logs lifecycle events without sensitive data.
 */
async function createWithPairingRetry(evolutionClient, storeId, normalizedPhone, settleMs, maxAttempts) {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const attemptStart = Date.now();

    logger.info({
      msg: 'Pairing attempt starting',
      storeId,
      attempt,
      maxAttempts,
    });

    let result;
    try {
      result = await evolutionClient.createInstance(storeId, normalizedPhone);
    } catch (err) {
      const elapsed = Date.now() - attemptStart;
      logger.warn({
        msg: 'Pairing create failed',
        storeId,
        attempt,
        elapsedMs: elapsed,
        errorType: isPairingFailure(err) ? 'pairing_failure' : 'create_error',
        statusCode: err.response?.status,
      });

      // If more attempts remain, clean up and retry.
      if (attempt < maxAttempts) {
        try { await evolutionClient.deleteInstance(storeId); } catch { /* best-effort */ }
        await waitForDeletion(evolutionClient, storeId);
        continue;
      }

      return mapUpstreamError(err);
    }

    const pairingCode = (result && result.qrcode && result.qrcode.pairingCode) || null;
    const qrBase64 = (result && result.qrcode && result.qrcode.base64) || null;

    if (!pairingCode) {
      // No pairing code returned — return whatever we have (may include QR).
      const elapsed = Date.now() - attemptStart;
      logger.info({
        msg: 'Pairing code not returned by Evolution',
        storeId,
        attempt,
        elapsedMs: elapsed,
        hasQr: !!qrBase64,
      });
      return {
        status: 200,
        body: { status: 'initializing', storeId, qr_code: qrBase64, pairing_code: null },
      };
    }

    // Wait for socket to settle before checking state.
    await new Promise((resolve) => setTimeout(resolve, settleMs));

    // Validate connection state — pairing code is only valid if socket is alive.
    let connectionState = 'close';
    try {
      const st = await evolutionClient.getConnectionState(storeId);
      connectionState = extractState(st);
    } catch {
      connectionState = 'close';
    }

    const elapsed = Date.now() - attemptStart;

    if (connectionState === 'open') {
      // Already connected (rare but possible if device paired very fast).
      logger.info({
        msg: 'Pairing completed during creation',
        storeId,
        attempt,
        elapsedMs: elapsed,
        connectionState,
      });
      return {
        status: 200,
        body: { status: 'connected', storeId, qr_code: null, pairing_code: null },
      };
    }

    if (connectionState === 'connecting') {
      // Socket is alive — pairing code is valid.
      logger.info({
        msg: 'Pairing code valid',
        storeId,
        attempt,
        elapsedMs: elapsed,
        connectionState,
      });
      return {
        status: 200,
        body: { status: 'initializing', storeId, qr_code: qrBase64, pairing_code: pairingCode },
      };
    }

    // Socket is closed — pairing code is dead. This is the 428/515 bug.
    logger.warn({
      msg: 'Pairing code invalidated — socket closed immediately',
      storeId,
      attempt,
      elapsedMs: elapsed,
      connectionState,
    });

    if (attempt < maxAttempts) {
      // Clean up and retry.
      try { await evolutionClient.deleteInstance(storeId); } catch { /* best-effort */ }
      await waitForDeletion(evolutionClient, storeId);
    }
  }

  // All attempts exhausted.
  logger.error({
    msg: 'Pairing failed — all attempts exhausted',
    storeId,
    maxAttempts,
  });

  return {
    status: 200,
    body: {
      status: 'failed',
      storeId,
      qr_code: null,
      pairing_code: null,
      error: 'pairing_failed',
      message: 'Could not establish a pairing session. The WhatsApp service may not support pairing for this number. Try scanning the QR code instead.',
    },
  };
}

module.exports = { connectSession, waitForDeletion, extractState, isPairingFailure };
