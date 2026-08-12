/**
 * Map an error from an upstream Evolution API call to a safe gateway response.
 *
 * Guarantees:
 *   - Evolution 400 -> gateway 400 (bad request, e.g. invalid number)
 *   - Evolution 409 -> gateway 409 (conflict, instance busy)
 *   - Timeout/abort -> gateway 504
 *   - Anything else -> gateway 502 (upstream unavailable)
 *
 * The returned body is always a static, safe payload. It never contains the raw
 * Evolution response, API keys, a phone number, a pairing code, or a stack trace.
 *
 * @param {Error & { code?: string, response?: { status?: number } }} err
 * @returns {{ status: number, body: { error: string, message: string } }}
 */
function mapUpstreamError(err) {
  const isTimeout =
    (err && err.code === 'ECONNABORTED') ||
    (err && typeof err.message === 'string' && /timeout/i.test(err.message));
  if (isTimeout) {
    return {
      status: 504,
      body: { error: 'upstream_timeout', message: 'WhatsApp service timed out. Please try again.' },
    };
  }

  const upstream = err && err.response && err.response.status;
  if (upstream === 400) {
    return {
      status: 400,
      body: { error: 'invalid_phone_number', message: 'Enter a valid international phone number.' },
    };
  }
  if (upstream === 409) {
    return {
      status: 409,
      body: { error: 'conflict', message: 'This WhatsApp session is already being set up. Please wait.' },
    };
  }

  return {
    status: 502,
    body: { error: 'upstream_error', message: 'WhatsApp service is currently unavailable. Please try again.' },
  };
}

module.exports = { mapUpstreamError };
