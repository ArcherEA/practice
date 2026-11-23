import { createFileRoute } from "@tanstack/react-router"

import { ProfilePage } from "@/features/community/profile/ProfilePage"
import { profileOptions } from "@/features/community/profileApi"
import { orNotFound, toHead } from "@/features/content/public/api"
import { requireModule } from "@/features/modules/api"

// Public member profile. Mirrors backend/app/modules/community/seo.py for the head.
export const Route = createFileRoute("/_public/u/$username")({
  beforeLoad: ({ context }) => requireModule(context.queryClient, "community"),
  loader: ({ context, params }) =>
    orNotFound(() =>
      context.queryClient.ensureQueryData(profileOptions(params.username)),
    ),
  head: ({ loaderData }) =>
    loaderData
      ? toHead({
          title: `${loaderData.display_name} (@${loaderData.username})`,
          description:
            loaderData.bio?.trim() ||
            `${loaderData.display_name} on the community.`,
        })
      : {},
  component: Profile,
})

function Profile() {
  const { username } = Route.useParams()
  return <ProfilePage username={username} />
}
