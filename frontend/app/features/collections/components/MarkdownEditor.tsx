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

// No typography plugin in the app, so the editable area styles its own blocks.
const CONTENT_CLASS = [
  "min-h-80 p-3 text-sm outline-none [&_p]:my-2",
  "[&_h1]:my-3 [&_h1]:text-2xl [&_h1]:font-semibold",
  "[&_h2]:my-3 [&_h2]:text-xl [&_h2]:font-semibold",
  "[&_h3]:my-2 [&_h3]:text-lg [&_h3]:font-semibold",
  "[&_ul]:list-disc [&_ol]:list-decimal [&_ol,&_ul]:my-2 [&_ol,&_ul]:pl-6",
  "[&_table]:my-3 [&_table]:w-full [&_table]:border-collapse",
  "[&_td,&_th]:border [&_td,&_th]:px-2 [&_td,&_th]:py-1 [&_th]:bg-muted",
].join(" ")

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
