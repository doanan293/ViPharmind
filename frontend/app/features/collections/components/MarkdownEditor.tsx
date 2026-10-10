import { Markdown } from "@tiptap/markdown"
import { TableKit } from "@tiptap/extension-table"
import {
  type Editor,
  EditorContent,
  useEditor,
  useEditorState,
} from "@tiptap/react"
import { StarterKit } from "@tiptap/starter-kit"
import { useEffect } from "react"

import { Skeleton } from "~/components/ui/skeleton"

import { EditorToolbar } from "./EditorToolbar"

const CONTENT_CLASS =
  "prose prose-sm dark:prose-invert min-h-80 max-w-none p-3 outline-none"

/** StarterKit keeps an empty paragraph at the end, which is not part of the document. */
function markdownOf(editor: Editor): string {
  return editor.getMarkdown().trimEnd()
}

/**
 * A rich-text editor whose value is Markdown, the format documents are stored in.
 *
 * Tiptap needs the DOM, so the editor appears after hydration; a skeleton stands in on the
 * server. A new `value` from outside (an uploaded file) replaces the content.
 */
export function MarkdownEditor({
  value,
  onChange,
  labelledBy,
}: {
  value: string
  onChange: (markdown: string) => void
  labelledBy: string
}) {
  const editor = useEditor({
    extensions: [
      StarterKit,
      Markdown,
      TableKit.configure({ table: { resizable: false } }),
    ],
    content: value,
    contentType: "markdown",
    immediatelyRender: false,
    editorProps: {
      attributes: {
        role: "textbox",
        "aria-multiline": "true",
        "aria-labelledby": labelledBy,
        class: CONTENT_CLASS,
      },
    },
    onUpdate: ({ editor: current }) => onChange(markdownOf(current)),
  })
  // Re-render the toolbar when the selection moves so active marks stay in sync.
  useEditorState({
    editor,
    selector: ({ editor: current }) => current?.state.selection,
  })

  useEffect(() => {
    if (editor === null || markdownOf(editor) === value) return
    editor.commands.setContent(value, { contentType: "markdown" })
  }, [editor, value])

  if (editor === null) {
    return <Skeleton className="h-80 w-full" />
  }
  return (
    <div className="overflow-hidden rounded-lg border focus-within:ring-3 focus-within:ring-ring/50">
      <EditorToolbar editor={editor} />
      <EditorContent editor={editor} />
    </div>
  )
}
