"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { signIn } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function LoginPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  // Signup redirects here with ?registered=true. The param is read through the
  // router (useSearchParams) rather than window.location: during a client-side
  // navigation this page renders before the browser URL is updated, so a
  // render-time read of window.location still sees the previous page. The
  // flag is latched into state (set-during-render, the "adjusting state on a
  // prop change" pattern) so the banner survives the effect below clearing the
  // param, which keeps a refresh from re-showing it (#323). Every route is
  // dynamically rendered (the root layout reads headers()), so no Suspense
  // boundary is needed for useSearchParams.
  const [registered, setRegistered] = useState(false)
  if (!registered && searchParams.get("registered") === "true") {
    setRegistered(true)
  }
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
            {registered && (
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
