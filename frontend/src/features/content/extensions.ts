import Image from "@tiptap/extension-image"
import Link from "@tiptap/extension-link"
import Placeholder from "@tiptap/extension-placeholder"
import StarterKit from "@tiptap/starter-kit"

/**
 * The editor schema. It must stay inside the backend allow-list
 * (backend/app/modules/content/body.py, docs/ARCHITECTURE.md):
 *   nodes  doc, paragraph, heading (1-3), bulletList, orderedList, listItem,
 *          blockquote, codeBlock, horizontalRule, hardBreak, image, text
 *   marks  bold, italic, strike, code, link
 * ProseMirror drops anything outside the schema on paste/parse, so keeping the
 * extension list small is what constrains the output.
 */

/** Link href rule, same as the backend: http(s), mailto or a single-slash path. */
export function isAllowedContentHref(url: string): boolean {
  const value = url.trim()
  for (const char of value) {
    const code = char.charCodeAt(0)
    if (code < 0x20 || code === 0x7f) return false
  }
  return /^(https?:|mailto:)/i.test(value) || /^\/(?!\/)/.test(value)
}

/** Image node with the `fileId` attribute the backend requires (stored as data-file-id). */
export const ContentImage = Image.extend({
  addAttributes() {
    // Same as Image's own attributes, minus width/height (the backend does not accept them).
    return {
      src: { default: null },
      alt: { default: null },
      title: { default: null },
      fileId: {
        default: null,
        parseHTML: (element: HTMLElement) =>
          element.getAttribute("data-file-id"),
        renderHTML: (attributes: { fileId?: string | null }) =>
          attributes.fileId ? { "data-file-id": attributes.fileId } : {},
      },
    }
  },
  // Only images that came from our uploads (they carry a file id) are accepted
  // when parsing pasted or dropped HTML; anything else would be rejected on save.
  parseHTML() {
    return [{ tag: "img[data-file-id]" }]
  },
})

export function createContentExtensions(placeholder = "Write something...") {
  return [
    StarterKit.configure({
      heading: { levels: [1, 2, 3] },
      // Bundled by StarterKit v3 but not on the backend allow-list.
      underline: false,
      // Link is added below with our own URL rules.
      link: false,
    }),
    Link.configure({
      openOnClick: false,
      autolink: false,
      linkOnPaste: true,
      defaultProtocol: "https",
      isAllowedUri: (url) => isAllowedContentHref(url),
    }),
    ContentImage.configure({ allowBase64: false }),
    Placeholder.configure({ placeholder }),
  ]
}
