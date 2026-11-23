import { useQuery } from "@tanstack/react-query"

import { configQueryOptions } from "./api"

export function useModules() {
  const { data, isLoading } = useQuery(configQueryOptions)
  const modules = data?.modules ?? []
  return {
    modules,
    isEnabled: (name: string) => modules.includes(name),
    isLoading,
  }
}
