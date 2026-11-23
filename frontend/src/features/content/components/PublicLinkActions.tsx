import { Copy, ExternalLink } from "lucide-react"

import { Button } from "@/components/ui/button"
import useCustomToast from "@/hooks/useCustomToast"
import { type ContentKind, publicPath } from "../api"

/** Copies text via a temporary textarea; works on non-secure (http) pages too. */
function copyWithTextarea(text: string): boolean {
  const area = document.createElement("textarea")
  area.value = text
  area.setAttribute("readonly", "")
  area.style.position = "fixed"
  area.style.opacity = "0"
  document.body.appendChild(area)
  area.select()
  try {
    // execCommand is deprecated but is the only option without the Clipboard API.
    return document.execCommand("copy")
  } finally {
    area.remove()
  }
}

interface PublicLinkActionsProps {
  kind: ContentKind
  /** The saved slug (not unsaved form edits). */
  slug: string
  published: boolean
  /** The slug field has changes that are not saved yet. */
  slugDirty?: boolean
}

/** "View on site" and "Copy link" for the editor; drafts show a muted hint. */
export function PublicLinkActions({
  kind,
  slug,
  published,
  slugDirty = false,
}: PublicLinkActionsProps) {
  const { showSuccessToast, showErrorToast } = useCustomToast()

  if (!published) {
    return (
      <span className="text-sm text-muted-foreground">Not published yet</span>
    )
  }

  const path = publicPath(kind, slug)
  const copy = async () => {
    const url = `${window.location.origin}${path}`
    try {
      // navigator.clipboard only exists on secure pages (https:// or localhost);
      // on plain http (e.g. an own server without TLS) fall back to execCommand.
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(url)
      } else if (!copyWithTextarea(url)) {
        throw new Error("copy failed")
      }
      showSuccessToast("Link copied")
    } catch {
      showErrorToast("Could not copy the link")
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button asChild variant="outline">
        <a href={path} target="_blank" rel="noopener">
          <ExternalLink />
          View on site
        </a>
      </Button>
      <Button type="button" variant="outline" onClick={copy}>
        <Copy />
        Copy link
      </Button>
      {slugDirty && (
        <span className="text-sm text-muted-foreground">
          Save to update the link
        </span>
      )}
    </div>
  )
}
