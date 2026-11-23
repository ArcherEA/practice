import { useMutation, useQueryClient } from "@tanstack/react-query"

import { UsersService } from "@/client"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { LoadingButton } from "@/components/ui/loading-button"
import { IMAGE_CONTENT_TYPES } from "@/features/files/constants"
import { FileUpload } from "@/features/files/FileUpload"
import { useFileUpload } from "@/features/files/useFileUpload"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { getInitials, handleError } from "@/utils"

const UserAvatar = () => {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { upload, progress, isUploading, error, reset } = useFileUpload()

  const refreshUser = () =>
    queryClient.invalidateQueries({ queryKey: ["currentUser"] })

  const setAvatar = useMutation({
    mutationFn: (fileId: string) =>
      UsersService.setAvatarMe({ body: { file_id: fileId } }),
    onSuccess: () => showSuccessToast("Profile picture updated"),
    onError: handleError.bind(showErrorToast),
    onSettled: refreshUser,
  })

  const removeAvatar = useMutation({
    mutationFn: () => UsersService.deleteAvatarMe(),
    onSuccess: () => showSuccessToast("Profile picture removed"),
    onError: handleError.bind(showErrorToast),
    onSettled: refreshUser,
  })

  const handleSelect = async (file: File) => {
    reset()
    const uploaded = await upload(file, {
      public: true,
      accept: IMAGE_CONTENT_TYPES,
    })
    if (uploaded) {
      setAvatar.mutate(uploaded.id)
    }
  }

  const busy = isUploading || setAvatar.isPending || removeAvatar.isPending

  return (
    <div className="max-w-md" data-testid="avatar-section">
      <h3 className="text-lg font-semibold py-4">Profile picture</h3>
      <div className="flex items-center gap-4">
        {/* key: re-mount when the URL changes so an earlier load error is forgotten */}
        <Avatar className="size-20" key={user?.avatar_url ?? "none"}>
          {user?.avatar_url && (
            <AvatarImage
              src={user.avatar_url}
              alt="Your profile picture"
              data-testid="settings-avatar-image"
            />
          )}
          <AvatarFallback className="bg-zinc-600 text-white text-xl">
            {getInitials(user?.full_name || user?.email || "User")}
          </AvatarFallback>
        </Avatar>
        <div className="flex flex-col gap-2">
          <FileUpload
            label={user?.avatar_url ? "Change picture" : "Upload new picture"}
            accept={IMAGE_CONTENT_TYPES.join(",")}
            onSelect={handleSelect}
            isUploading={isUploading || setAvatar.isPending}
            progress={progress}
            error={error}
            testId="avatar-upload"
          />
          {user?.avatar_url && (
            <LoadingButton
              type="button"
              variant="ghost"
              className="w-fit"
              loading={removeAvatar.isPending}
              disabled={busy}
              onClick={() => removeAvatar.mutate()}
            >
              Remove
            </LoadingButton>
          )}
        </div>
      </div>
    </div>
  )
}

export default UserAvatar
