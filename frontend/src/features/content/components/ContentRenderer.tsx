import { EditorContent, type JSONContent, useEditor } from "@tiptap/react"
import { useEffect, useMemo } from "react"

import { cn } from "@/lib/utils"
import { toEditorContent } from "../body"
import { createContentExtensions } from "../extensions"
import "../content.css"

interface ContentRendererProps {
  /** Tiptap JSON as returned by the API (or straight from the editor). */
  body: { [key: string]: unknown } | JSONContent | null | undefined
  className?: string
}

/**
 * Read-only renderer for a content body. It renders the JSON through the same
 * schema as the editor (nothing outside the allow-list can appear) and never
 * uses dangerouslySetInnerHTML. Task 011 reuses it for public pages.
 */
export function ContentRenderer({ body, className }: ContentRendererProps) {
  const extensions = useMemo(() => createContentExtensions(""), [])
  const content = useMemo(
    () => toEditorContent(body as { [key: string]: unknown } | null),
    [body],
  )
  const editor = useEditor({
    extensions,
    content,
    editable: false,
    immediatelyRender: false,
  })

  useEffect(() => {
    if (editor && !editor.isDestroyed) {
      editor.commands.setContent(content, { emitUpdate: false })
    }
  }, [editor, content])

  return (
    <EditorContent
      editor={editor}
      data-testid="content-renderer"
      className={cn("content-prose", className)}
    />
  )
}
