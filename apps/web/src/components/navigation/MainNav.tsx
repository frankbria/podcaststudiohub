"use client"

import { useSession, signOut } from "next-auth/react"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { HugeiconsIcon } from "@hugeicons/react"
import { UserCircle02Icon, Logout01Icon, Home01Icon, RssIcon } from "@hugeicons/core-free-icons"
import { ThemeToggle } from "@/components/ThemeToggle"

const NAV_LINKS = [
  { href: "/dashboard", label: "Dashboard", icon: Home01Icon },
  { href: "/distribution", label: "Distribution", icon: RssIcon },
]

export function MainNav() {
  const router = useRouter()
  const { data: session, status } = useSession()
  const [isLoggingOut, setIsLoggingOut] = useState(false)

  if (status === "unauthenticated") return null
  if (status === "loading") return null

  const handleLogout = async () => {
    setIsLoggingOut(true)
    try {
      await signOut({ redirect: false })
      localStorage.clear()
      sessionStorage.clear()
      router.push("/login")
    } finally {
      setIsLoggingOut(false)
    }
  }

  return (
    <nav className="border-b bg-background" aria-label="Main navigation">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <div className="flex items-center gap-4">
            <a href="/dashboard" className="text-2xl font-bold text-primary">
              Podcastfy Studio
            </a>
            <div className="hidden sm:flex items-center gap-1">
              {NAV_LINKS.map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-all hover:bg-muted hover:text-foreground"
                >
                  <HugeiconsIcon icon={link.icon} size={16} />
                  {link.label}
                </a>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-4">
            <ThemeToggle />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="rounded-full"
                  aria-label="User menu"
                  disabled={isLoggingOut}
                >
                  <HugeiconsIcon icon={UserCircle02Icon} size={20} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel className="font-normal">
                  <div className="flex flex-col gap-1">
                    <p className="font-medium">{session?.user?.name ?? "User"}</p>
                    <p className="text-xs text-muted-foreground">
                      {session?.user?.email}
                    </p>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleLogout} disabled={isLoggingOut}>
                  <HugeiconsIcon icon={Logout01Icon} size={16} />
                  Logout
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </div>
    </nav>
  )
}
