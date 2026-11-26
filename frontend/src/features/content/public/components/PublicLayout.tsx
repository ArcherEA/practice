import { useQuery } from "@tanstack/react-query"
import { Link, Outlet } from "@tanstack/react-router"

import { Appearance } from "@/components/Common/Appearance"
import { Button } from "@/components/ui/button"
import { ShopHeader } from "@/features/commerce/storefront/components/ShopHeader"
import { NotificationBell } from "@/features/community/notifications/NotificationBell"
import { configQueryOptions } from "@/features/modules/api"
import { useModules } from "@/features/modules/useModules"
import { isLoggedIn } from "@/hooks/useAuth"

/** Header + footer for the public site (no login needed). */
export function PublicLayout() {
  const { data: config } = useQuery(configQueryOptions)
  const siteName = config?.project_name ?? ""
  const loggedIn = isLoggedIn()
  const { isEnabled } = useModules()
  const blog = isEnabled("content")
  const shop = isEnabled("commerce")

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <Link to={blog ? "/blog" : "/shop"} className="text-lg font-semibold">
            {siteName}
          </Link>
          <nav
            aria-label="Main"
            className="flex flex-wrap items-center gap-2 text-sm"
          >
            {blog && (
              <Button variant="ghost" size="sm" asChild>
                <Link to="/blog">Blog</Link>
              </Button>
            )}
            {shop && <ShopHeader />}
            <NotificationBell />
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
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:py-12">
        <Outlet />
      </main>
      <footer className="border-t py-6 text-center text-sm text-muted-foreground">
        &copy; {new Date().getFullYear()} {siteName}
      </footer>
    </div>
  )
}

export function PublicNotFound() {
  const { isEnabled } = useModules()
  const blog = isEnabled("content")
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
        {blog ? (
          <Link to="/blog">Back to the blog</Link>
        ) : (
          <Link to="/shop">Back to the shop</Link>
        )}
      </Button>
    </div>
  )
}
