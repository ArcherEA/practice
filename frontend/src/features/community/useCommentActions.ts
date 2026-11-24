import { useMutation, useQueryClient } from "@tanstack/react-query"

import { CommunityService, type ReportCreate } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"
import { type CommentTarget, communityKeys } from "./api"

/**
 * Mutations for the comment section of one post or page. Each one shows the
 * API's `detail` (rate limit, suspension, ...) as a toast on failure and
 * refetches the comment list afterwards.
 */
export function useCommentActions(target: CommentTarget) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: communityKeys.comments(target) })
  const onError = (err: Error) => {
    handleError.call(showErrorToast, err)
    // A 403 may mean the member was suspended meanwhile.
    queryClient.invalidateQueries({ queryKey: communityKeys.mySuspension })
  }

  const create = useMutation({
    mutationFn: ({ body, parentId }: { body: string; parentId?: string }) => {
      const data = { body, parent_id: parentId }
      return target.type === "post"
        ? CommunityService.createPostComment({
            path: { post_id: target.id },
            body: data,
          })
        : CommunityService.createPageComment({
            path: { page_id: target.id },
            body: data,
          })
    },
    onError,
    onSettled: refresh,
  })

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) =>
      CommunityService.updateComment({
        path: { comment_id: id },
        body: { body },
      }),
    onError,
    onSettled: refresh,
  })

  const remove = useMutation({
    mutationFn: (id: string) =>
      CommunityService.deleteComment({ path: { comment_id: id } }),
    onSuccess: () => showSuccessToast("Comment deleted"),
    onError,
    onSettled: refresh,
  })

  const likeComment = useMutation({
    mutationFn: ({ id, like }: { id: string; like: boolean }) =>
      like
        ? CommunityService.likeComment({ path: { comment_id: id } })
        : CommunityService.unlikeComment({ path: { comment_id: id } }),
    onError,
    onSettled: refresh,
  })

  const likePost = useMutation({
    mutationFn: (like: boolean) =>
      like
        ? CommunityService.likePost({ path: { post_id: target.id } })
        : CommunityService.unlikePost({ path: { post_id: target.id } }),
    onError,
    onSettled: refresh,
  })

  const report = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ReportCreate }) =>
      CommunityService.reportComment({ path: { comment_id: id }, body: data }),
    onSuccess: () =>
      showSuccessToast("Thanks, the moderators will take a look"),
    onError,
  })

  return { create, update, remove, likeComment, likePost, report }
}
