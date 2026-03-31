const { normalizePayload } = require("./helpers")

function summarizeReport(value) {
  return `report:${normalizePayload(value)}`
}

module.exports = { summarizeReport }
