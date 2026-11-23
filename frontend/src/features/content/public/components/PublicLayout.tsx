import { useQuery } from "@tanstack/react-query"
import { Link, Outlet } from "@tanstack/react-router"

import { Appearance } from "@/components/Common/Appearance"
import { Button } from "@/components/ui/button"
import { configQueryOptions } from "@/features/modules/api"
import { isLoggedIn } from "@/hooks/useAuth"
import { PublicSidebar } from "./PublicSidebar"

/** Header + sidebar + footer for the public site (no login needed). */
export function PublicLayout() {
  const { data: config } = useQuery(configQueryOptions)
  const siteName = config?.project_name ?? ""
  const loggedIn = isLoggedIn()

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="border-b">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <Link to="/blog" className="text-lg font-semibold">
            {siteName}
          </Link>
          <nav
            aria-label="Main"
            className="flex flex-wrap items-center gap-2 text-sm"
          >
            <Button variant="ghost" size="sm" asChild>
              <Link to="/blog">Blog</Link>
            </Button>
            {loggedIn ? (
              <Button variant="outline" size="sm" asChild>
                <Link to="/">Dashboard</Link>
              </Button>
            ) : (
              <Button variant="outline" size="sm" asChild>
                <Link to="/login">Log in</Link>
              </Button>
            )}
            <Appearance />
          </nav>
        </div>
      </header>
      <div className="mx-auto grid w-full max-w-6xl flex-1 grid-cols-1 gap-10 px-4 py-8 sm:py-12 lg:grid-cols-[minmax(0,1fr)_17rem] lg:gap-12">
        <main className="min-w-0">
          <Outlet />
        </main>
        <PublicSidebar />
      </div>
      <footer className="border-t py-6 text-center text-sm text-muted-foreground">
        &copy; {new Date().getFullYear()} {siteName}
      </footer>
    </div>
  )
}

export function PublicNotFound() {
  return (
    <div
      className="flex flex-col items-center gap-3 py-16 text-center"
      data-testid="not-found"
    >
      <span className="text-6xl font-bold">404</span>
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="text-muted-foreground">
        We could not find what you were looking for.
      </p>
      <Button asChild className="mt-2">
        <Link to="/blog">Back to the blog</Link>
      </Button>
    </div>
  )
}
