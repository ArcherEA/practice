import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"

import { CommunityService, type ProfilePublic } from "@/client"
import { Button } from "@/components/ui/button"
import { LoadingButton } from "@/components/ui/loading-button"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"
import { profileKeys } from "../profileApi"

/** Follow / Unfollow for someone else's profile; a login link for visitors; nothing on your own. */
export function FollowButton({
  profile,
  returnTo,
}: {
  profile: ProfilePublic
  returnTo: string
}) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  const toggle = useMutation({
    mutationFn: async (follow: boolean) =>
      (
        await (follow
          ? CommunityService.followUser({
              path: { username: profile.username },
            })
          : CommunityService.unfollowUser({
              path: { username: profile.username },
            }))
      ).data,
    onSuccess: (state) => {
      queryClient.setQueryData<ProfilePublic>(
        profileKeys.profile(profile.username),
        (old) =>
          old && {
            ...old,
            followed_by_me: state.following,
            follower_count: state.follower_count,
          },
      )
      queryClient.invalidateQueries({
        queryKey: profileKeys.followers(profile.username),
      })
      queryClient.invalidateQueries({ queryKey: profileKeys.activity })
    },
    onError: handleError.bind(showErrorToast),
  })

  if (!isLoggedIn()) {
    return (
      <Button variant="outline" asChild>
        <Link to="/login" search={{ redirect: returnTo }}>
          Log in to follow
        </Link>
      </Button>
    )
  }
  if (!user || user.username === profile.username) return null

  const following = profile.followed_by_me === true
  return (
    <LoadingButton
      variant={following ? "outline" : "default"}
      loading={toggle.isPending}
      aria-pressed={following}
      onClick={() => toggle.mutate(!following)}
    >
      {following ? "Unfollow" : "Follow"}
    </LoadingButton>
  )
}
