import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { AxiosError } from "axios"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"
import { client } from "./client/client.gen"
import { ThemeProvider } from "./components/theme-provider"
import { Toaster } from "./components/ui/sonner"
import "./index.css"
import { routeTree } from "./routeTree.gen"

client.setConfig({
  baseURL: import.meta.env.VITE_API_URL ?? "",
  auth: () => localStorage.getItem("access_token") || "",
})

// A 403 from the community module is a rule ("You are suspended from
// commenting", moderators acting on an admin's content), not a dead session:
// show it, don't log out. Other 403s (and every 401) still end the session.
// The backend also answers 403 "Could not validate credentials" for a bad or expired
// token — that one is a dead session everywhere, so it still logs out.
const isCommunityRule = (error: AxiosError) =>
  error.response?.status === 403 &&
  (error.config?.url ?? "").includes("/api/v1/community/") &&
  (error.response?.data as { detail?: unknown } | undefined)?.detail !==
    "Could not validate credentials"

const isAuthError = (error: Error) =>
  error instanceof AxiosError &&
  [401, 403].includes(error.response?.status ?? 0) &&
  !isCommunityRule(error)

const handleApiError = (error: Error) => {
  if (isAuthError(error)) {
    localStorage.removeItem("access_token")
    window.location.href = "/login"
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Retrying a 401/403 can't succeed; fail fast so handleApiError logs out
      // immediately instead of after ~7s of retries (task 008).
      retry: (failureCount, error) => !isAuthError(error) && failureCount < 3,
    },
  },
  queryCache: new QueryCache({
    onError: handleApiError,
  }),
  mutationCache: new MutationCache({
    onError: handleApiError,
  }),
})

const router = createRouter({ routeTree, context: { queryClient } })
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

// On public content URLs the backend injects SEO tags into index.html for crawlers and
// link previews (task 011). Route head() functions manage the description from here on,
// so drop the server's copy to avoid two <meta name="description"> tags. Canonical and
// Open Graph tags are only set by the server and stay.
for (const el of document.querySelectorAll('meta[name="description"]')) {
  el.remove()
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <Toaster richColors closeButton />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
