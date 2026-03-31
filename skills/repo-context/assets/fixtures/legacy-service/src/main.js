const { createRouter } = require("./router")
const { summarizeReport } = require("./legacy-reporting")

function start() {
  const router = createRouter()
  return summarizeReport(router.name)
}

module.exports = { start }
