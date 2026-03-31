import { EXPORT_FORMATS } from "./editor-presets"
import { TEMPLATE_IDS } from "./paper-templates"

export function exportPdf(templateId: string) {
  return `pdf:${templateId}:${TEMPLATE_IDS.join(",")}:${EXPORT_FORMATS.join(",")}`
}

export function renderPaperSummary(templateId: string) {
  return `summary:${templateId}`
}
