import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useRouter } from "@tanstack/react-router"

import {
  type Body_login_login_access_token as AccessToken,
  LoginService,
  type UserPublic,
  type UserRegister,
  type UserRole,
  UsersService,
} from "@/client"
import {
  canDeleteUser,
  canEditUser,
  canManageUsers,
  hasRole,
} from "@/features/auth/permissions"
import { safeRedirect } from "@/features/auth/redirect"
import { handleError } from "@/utils"
import useCustomToast from "./useCustomToast"

const isLoggedIn = () => {
  return localStorage.getItem("access_token") !== null
}

const useAuth = () => {
  const navigate = useNavigate()
  const router = useRouter()
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  const { data: user } = useQuery<UserPublic | null, Error>({
    queryKey: ["currentUser"],
    queryFn: async () => (await UsersService.readUserMe()).data,
    enabled: isLoggedIn(),
  })

  const signUpMutation = useMutation({
    mutationFn: (data: UserRegister) =>
      UsersService.registerUser({ body: data }),
    onSuccess: () => {
      navigate({ to: "/login" })
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
  })

  const login = async (data: AccessToken) => {
    const response = await LoginService.loginAccessToken({
      body: data,
    })
    localStorage.setItem("access_token", response.data.access_token)
  }

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: () => {
      // `?redirect=` brings the visitor back to where they came from
      // (only same-site paths are accepted).
      const target = safeRedirect(
        new URLSearchParams(window.location.search).get("redirect"),
      )
      if (target) router.history.push(target)
      else navigate({ to: "/" })
    },
    onError: handleError.bind(showErrorToast),
  })

  const logout = () => {
    localStorage.removeItem("access_token")
    navigate({ to: "/login" })
  }

  return {
    hasRole: (required: UserRole) => hasRole(user, required),
    canManageUsers: canManageUsers(user),
    canEditUser: (target: UserPublic) => canEditUser(user, target),
    canDeleteUser: (target: UserPublic) => canDeleteUser(user, target),
    signUpMutation,
    loginMutation,
    logout,
    user,
  }
}

export { isLoggedIn }
export default useAuth
