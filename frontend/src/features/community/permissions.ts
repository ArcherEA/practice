import type { UserPublic } from "@/client"
import { hasRole } from "@/features/auth/permissions"

/**
 * Who may use the moderation screen: moderator, admin and superuser (mirrors
 * the backend `require_role(UserRole.moderator)`). Editors are NOT included:
 * editor and moderator are siblings.
 */
export const canModerate = (
  user:
    | Partial<Pick<UserPublic, "id" | "role" | "is_superuser">>
    | null
    | undefined,
): boolean => hasRole(user, "moderator")
