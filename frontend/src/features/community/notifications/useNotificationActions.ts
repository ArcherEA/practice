import { useMutation, useQueryClient } from "@tanstack/react-query"

import { CommunityService } from "@/client"
import { notificationKeys } from "../profileApi"

/** "Mark all read" and "mark one read"; both refresh the badge and the lists. */
export function useNotificationActions() {
  const queryClient = useQueryClient()
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: notificationKeys.all })

  const markAllRead = useMutation({
    mutationFn: async () =>
      (await CommunityService.readAllNotifications()).data,
    onSuccess: (data) =>
      queryClient.setQueryData(notificationKeys.unread, data),
    onSettled: refresh,
  })

  const markRead = useMutation({
    mutationFn: (id: string) =>
      CommunityService.readNotification({ path: { notification_id: id } }),
    onSettled: refresh,
  })

  return { markAllRead, markRead }
}
