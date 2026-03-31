type EditorShellProps = {
  summary: string
}

export function EditorShell({ summary }: EditorShellProps) {
  return <div>{summary}</div>
}

export function ExportToolbar({ onExport }: { onExport: () => void }) {
  return <button onClick={onExport}>Export</button>
}
