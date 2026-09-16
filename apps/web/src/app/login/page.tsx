"use client"

import { useState, useEffect, useSyncExternalStore } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { signIn } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

// useSyncExternalStore with a no-op subscription: false during SSR/hydration, true after.
const subscribeNever = () => () => {}

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  // Signup redirects here with ?registered=true. Read window.location.search
  // (not useSearchParams, which forces a build-time Suspense boundary — same
  // pattern as the distribution page). The server render can't see the URL, so
  // the banner is gated on hydration to keep the server and client trees
  // identical; the effect then clears the param so a refresh doesn't re-show
  // the banner (#323).
  const [registered] = useState(
    () =>
      typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("registered") === "true"
  )
  const hydrated = useSyncExternalStore(subscribeNever, () => true, () => false)
  useEffect(() => {
    if (registered) window.history.replaceState({}, "", window.location.pathname)
  }, [registered])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      const result = await signIn("credentials", {
        email,
        password,
        redirect: false,
      })

      if (result?.error) {
        setError("Invalid email or password")
      } else {
        router.push("/dashboard")
      }
    } catch {
      setError("An error occurred. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <main id="main-content" className="min-h-screen flex items-center justify-center bg-background">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Podcastfy Studio</CardTitle>
          <CardDescription>Sign in to your account</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {hydrated && registered && (
              <div role="status" className="rounded-md bg-muted p-2 text-sm text-foreground">
                Account created. Please sign in.
              </div>
            )}
            <div>
              <Label htmlFor="email" className="mb-1">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={loading}
                aria-invalid={error ? "true" : undefined}
                aria-describedby={error ? "login-error" : undefined}
              />
            </div>
            <div>
              <Label htmlFor="password" className="mb-1">
                Password
              </Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={loading}
                aria-invalid={error ? "true" : undefined}
                aria-describedby={error ? "login-error" : undefined}
              />
            </div>
            {error && (
              <div id="login-error" role="alert" aria-live="assertive" className="text-destructive text-sm">
                {error}
              </div>
            )}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Signing in..." : "Sign In"}
            </Button>
            <div className="text-center text-sm text-muted-foreground">
              Don&apos;t have an account?{" "}
              <Link href="/signup" className="text-primary hover:underline">
                Sign up
              </Link>
            </div>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
