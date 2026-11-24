import type { UserPublic } from "@/client"
import { hasRole } from "@/features/auth/permissions"

/** Who may use the content editor: editor, admin and superuser (mirrors the backend). */
export const canManageContent = (
  user:
    | Partial<Pick<UserPublic, "id" | "role" | "is_superuser">>
    | null
    | undefined,
): boolean => hasRole(user, "editor")
