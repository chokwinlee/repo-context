import { EditorShell, ExportToolbar } from "../../components/editor-shell"
import { exportPdf } from "../../lib/paper-export"

export default function EditorPage() {
  return (
    <section>
      <ExportToolbar onExport={() => exportPdf("editor")} />
      <EditorShell summary="editor" />
    </section>
  )
}
