import { EditorShell } from "../components/editor-shell"
import { renderPaperSummary } from "../lib/paper-export"

export default function HomePage() {
  return <EditorShell summary={renderPaperSummary("starter")} />
}
