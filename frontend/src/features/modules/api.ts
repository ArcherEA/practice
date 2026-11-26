import type { QueryClient } from "@tanstack/react-query"
import { notFound } from "@tanstack/react-router"

import { UtilsService } from "@/client"

export const configQueryOptions = {
  queryKey: ["config"],
  queryFn: async () => (await UtilsService.getPublicConfig()).data,
  staleTime: Number.POSITIVE_INFINITY,
}

/**
 * Route guard for module pages. Use in a route's `beforeLoad`:
 *   beforeLoad: ({ context }) => requireModule(context.queryClient, "items")
 * Renders the NotFound page when the module is disabled.
 */
/** Like `requireModule`, but passes when at least one of the modules is enabled. */
export async function requireAnyModule(
  queryClient: QueryClient,
  names: string[],
) {
  const config = await queryClient.ensureQueryData(configQueryOptions)
  if (!names.some((name) => config.modules.includes(name))) {
    throw notFound()
  }
}

export async function requireModule(queryClient: QueryClient, name: string) {
  const config = await queryClient.ensureQueryData(configQueryOptions)
  if (!config.modules.includes(name)) {
    throw notFound()
  }
}
