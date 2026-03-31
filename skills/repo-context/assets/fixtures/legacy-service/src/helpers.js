function normalizePayload(value) {
  return String(value).trim().toLowerCase()
}

module.exports = { normalizePayload }
