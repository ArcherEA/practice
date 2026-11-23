import { Copy, ExternalLink } from "lucide-react"

import { Button } from "@/components/ui/button"
import useCustomToast from "@/hooks/useCustomToast"
import { type ContentKind, publicPath } from "../api"

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
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${path}`)
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
