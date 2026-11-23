import {
  type Editor,
  EditorContent,
  type JSONContent,
  useEditor,
  useEditorState,
} from "@tiptap/react"
import {
  Bold,
  Code,
  Code2,
  CornerDownLeft,
  Heading1,
  Heading2,
  Heading3,
  ImagePlus,
  Italic,
  Link as LinkIcon,
  List,
  ListOrdered,
  type LucideIcon,
  Minus,
  Quote,
  Redo2,
  Strikethrough,
  Undo2,
} from "lucide-react"
import { useMemo, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { IMAGE_CONTENT_TYPES } from "@/features/files/constants"
import { useFileUpload } from "@/features/files/useFileUpload"
import { cn } from "@/lib/utils"
import { fileContentUrl } from "../body"
import { createContentExtensions, isAllowedContentHref } from "../extensions"
import "../content.css"

interface ToolbarButtonProps {
  label: string
  icon: LucideIcon
  active?: boolean
  disabled?: boolean
  onClick: () => void
}

function ToolbarButton({
  label,
  icon: Icon,
  active = false,
  disabled = false,
  onClick,
}: ToolbarButtonProps) {
  return (
    <Button
      type="button"
      variant={active ? "secondary" : "ghost"}
      size="icon"
      className="size-8"
      aria-label={label}
      aria-pressed={active}
      title={label}
      disabled={disabled}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      <Icon />
    </Button>
  )
}

function Divider() {
  return <div className="mx-1 h-5 w-px bg-border" aria-hidden="true" />
}

function Toolbar({ editor }: { editor: Editor }) {
  const state = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      bold: e.isActive("bold"),
      italic: e.isActive("italic"),
      strike: e.isActive("strike"),
      code: e.isActive("code"),
      h1: e.isActive("heading", { level: 1 }),
      h2: e.isActive("heading", { level: 2 }),
      h3: e.isActive("heading", { level: 3 }),
      bulletList: e.isActive("bulletList"),
      orderedList: e.isActive("orderedList"),
      blockquote: e.isActive("blockquote"),
      codeBlock: e.isActive("codeBlock"),
      link: e.isActive("link"),
      canUndo: e.can().undo(),
      canRedo: e.can().redo(),
    }),
  })
  const { upload, isUploading, error: uploadError } = useFileUpload()
  const imageInputRef = useRef<HTMLInputElement>(null)
  const [linkOpen, setLinkOpen] = useState(false)
  const [linkUrl, setLinkUrl] = useState("")
  const [linkError, setLinkError] = useState<string | null>(null)

  const chain = () => editor.chain().focus()

  const openLink = () => {
    setLinkUrl((editor.getAttributes("link").href as string | undefined) ?? "")
    setLinkError(null)
    setLinkOpen(true)
  }

  const applyLink = () => {
    const url = linkUrl.trim()
    if (!url) {
      chain().extendMarkRange("link").unsetLink().run()
      setLinkOpen(false)
      return
    }
    if (!isAllowedContentHref(url)) {
      setLinkError("Use an http://, https:// or mailto: address, or a /path.")
      return
    }
    chain().extendMarkRange("link").setLink({ href: url.trim() }).run()
    setLinkOpen(false)
  }

  const removeLink = () => {
    chain().extendMarkRange("link").unsetLink().run()
    setLinkOpen(false)
  }

  const onImageSelected = async (file: File) => {
    const uploaded = await upload(file, {
      public: true,
      accept: IMAGE_CONTENT_TYPES,
    })
    if (!uploaded) return
    const alt = file.name.replace(/\.[^.]+$/, "").slice(0, 200)
    chain()
      .insertContent({
        type: "image",
        attrs: { fileId: uploaded.id, src: fileContentUrl(uploaded.id), alt },
      })
      .run()
  }

  return (
    <div className="border-b">
      <div
        role="toolbar"
        aria-label="Formatting"
        className="flex flex-wrap items-center gap-0.5 p-1"
      >
        <ToolbarButton
          label="Bold"
          icon={Bold}
          active={state.bold}
          onClick={() => chain().toggleBold().run()}
        />
        <ToolbarButton
          label="Italic"
          icon={Italic}
          active={state.italic}
          onClick={() => chain().toggleItalic().run()}
        />
        <ToolbarButton
          label="Strikethrough"
          icon={Strikethrough}
          active={state.strike}
          onClick={() => chain().toggleStrike().run()}
        />
        <ToolbarButton
          label="Inline code"
          icon={Code}
          active={state.code}
          onClick={() => chain().toggleCode().run()}
        />
        <Divider />
        <ToolbarButton
          label="Heading 1"
          icon={Heading1}
          active={state.h1}
          onClick={() => chain().toggleHeading({ level: 1 }).run()}
        />
        <ToolbarButton
          label="Heading 2"
          icon={Heading2}
          active={state.h2}
          onClick={() => chain().toggleHeading({ level: 2 }).run()}
        />
        <ToolbarButton
          label="Heading 3"
          icon={Heading3}
          active={state.h3}
          onClick={() => chain().toggleHeading({ level: 3 }).run()}
        />
        <Divider />
        <ToolbarButton
          label="Bullet list"
          icon={List}
          active={state.bulletList}
          onClick={() => chain().toggleBulletList().run()}
        />
        <ToolbarButton
          label="Numbered list"
          icon={ListOrdered}
          active={state.orderedList}
          onClick={() => chain().toggleOrderedList().run()}
        />
        <ToolbarButton
          label="Quote"
          icon={Quote}
          active={state.blockquote}
          onClick={() => chain().toggleBlockquote().run()}
        />
        <ToolbarButton
          label="Code block"
          icon={Code2}
          active={state.codeBlock}
          onClick={() => chain().toggleCodeBlock().run()}
        />
        <ToolbarButton
          label="Horizontal rule"
          icon={Minus}
          onClick={() => chain().setHorizontalRule().run()}
        />
        <ToolbarButton
          label="Line break"
          icon={CornerDownLeft}
          onClick={() => chain().setHardBreak().run()}
        />
        <Divider />
        <ToolbarButton
          label="Link"
          icon={LinkIcon}
          active={state.link}
          onClick={openLink}
        />
        <ToolbarButton
          label="Insert image"
          icon={ImagePlus}
          disabled={isUploading}
          onClick={() => imageInputRef.current?.click()}
        />
        <input
          ref={imageInputRef}
          type="file"
          accept={IMAGE_CONTENT_TYPES.join(",")}
          className="sr-only"
          tabIndex={-1}
          aria-label="Image file"
          data-testid="editor-image-input"
          onChange={(e) => {
            const file = e.target.files?.[0]
            e.target.value = ""
            if (file) void onImageSelected(file)
          }}
        />
        <Divider />
        <ToolbarButton
          label="Undo"
          icon={Undo2}
          disabled={!state.canUndo}
          onClick={() => chain().undo().run()}
        />
        <ToolbarButton
          label="Redo"
          icon={Redo2}
          disabled={!state.canRedo}
          onClick={() => chain().redo().run()}
        />
      </div>
      {linkOpen && (
        // Not a <form>: the editor lives inside the page's own form, and a
        // nested submit would bubble up and save the post.
        <div
          data-testid="link-bar"
          className="flex flex-wrap items-center gap-2 border-t p-2"
        >
          <Input
            aria-label="Link URL"
            placeholder="https://example.com"
            value={linkUrl}
            onChange={(e) => {
              setLinkUrl(e.target.value)
              setLinkError(null)
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault()
                applyLink()
              }
            }}
            className="h-8 max-w-sm"
            autoFocus
          />
          <Button type="button" size="sm" onClick={applyLink}>
            Apply link
          </Button>
          {state.link && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={removeLink}
            >
              Remove link
            </Button>
          )}
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setLinkOpen(false)}
          >
            Cancel
          </Button>
          {linkError && (
            <p role="alert" className="w-full text-sm text-destructive">
              {linkError}
            </p>
          )}
        </div>
      )}
      {(isUploading || uploadError) && (
        <p
          role={uploadError ? "alert" : "status"}
          className={cn(
            "border-t px-3 py-1.5 text-sm",
            uploadError ? "text-destructive" : "text-muted-foreground",
          )}
        >
          {uploadError ?? "Uploading image..."}
        </p>
      )}
    </div>
  )
}

interface RichTextEditorProps {
  /** Initial document. Changing it later does not reset the editor; remount with a key instead. */
  initialContent: JSONContent
  onChange: (doc: JSONContent) => void
  className?: string
}

/** Tiptap body editor with a toolbar. Output stays inside the backend allow-list. */
export function RichTextEditor({
  initialContent,
  onChange,
  className,
}: RichTextEditorProps) {
  const extensions = useMemo(() => createContentExtensions(), [])
  const editor = useEditor({
    extensions,
    content: initialContent,
    immediatelyRender: false,
    editorProps: {
      attributes: {
        "aria-label": "Body",
        role: "textbox",
        "aria-multiline": "true",
        class: "min-h-[320px] px-4 py-3",
      },
    },
    onUpdate: ({ editor: e }) => onChange(e.getJSON()),
  })

  if (!editor) return null

  return (
    <div
      className={cn(
        "rounded-md border bg-background focus-within:ring-[3px] focus-within:ring-ring/30",
        className,
      )}
    >
      <Toolbar editor={editor} />
      <EditorContent
        editor={editor}
        data-testid="rich-text-editor"
        className="content-prose"
      />
    </div>
  )
}
