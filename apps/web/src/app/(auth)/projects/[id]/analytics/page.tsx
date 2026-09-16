"use client"

import { useState, useEffect } from "react"
import { useRouter, useParams } from "next/navigation"
import { useSession } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { showErrorToast } from "@/lib/toast"
import { AnalyticsSkeleton } from "@/components/skeletons/AnalyticsSkeleton"
import { EmptyState } from "@/components/empty-state/EmptyState"
import { HugeiconsIcon } from "@hugeicons/react"
import { Analytics01Icon, Download01Icon, PlayIcon, MusicNote01Icon } from "@hugeicons/core-free-icons"

interface WeeklyDownload {
  week: string
  downloads: number
}

interface TopEpisode {
  episode_id: string
  downloads: number
}

interface Analytics {
  project_id: string
  period: { from: string; to: string; days: number }
  summary: {
    total_downloads: number
    total_plays: number
    total_listen_hours: number
  }
  trends: { weekly_downloads: WeeklyDownload[] }
  top_episodes: TopEpisode[]
}

// Backend calls go through the same-origin /api/proxy handler, which injects
// the bearer token server-side from the httpOnly cookie — no client token (#212).
// Returns null when the request failed; the error toast has already been shown.
async function fetchAnalytics(
  projectId: string,
  days: string
): Promise<Analytics | "not-found" | null> {
  try {
    const response = await fetch(`/api/proxy/projects/${projectId}/analytics?days=${days}`)
    if (response.ok) return (await response.json()) as Analytics
    if (response.status === 404) return "not-found"
    showErrorToast("Failed to load analytics")
    return null
  } catch (error) {
    console.error("Failed to load analytics:", error)
    showErrorToast("Failed to load analytics: Network error")
    return null
  }
}

export default function ProjectAnalyticsPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const { status: authStatus } = useSession()
  const [days, setDays] = useState("30")
  // The loaded result remembers which project/period it belongs to, so
  // "loading" is derived: any change of [id] (App Router reuses this page
  // instance) or period shows the skeleton until the matching response lands.
  const query = `${params.id}:${days}`
  const [loaded, setLoaded] = useState<{
    query: string
    analytics: Analytics | null
    notFound: boolean
  } | null>(null)
  const loading = loaded?.query !== query
  const analytics = loaded?.analytics ?? null
  const notFound = loaded?.notFound ?? false

  useEffect(() => {
    if (authStatus !== "authenticated") return
    let ignore = false
    fetchAnalytics(params.id, days).then((result) => {
      if (ignore) return
      setLoaded((prev) => ({
        query,
        // A failed reload keeps the previous data on screen, as before.
        analytics: result && result !== "not-found" ? result : (prev?.analytics ?? null),
        notFound: result === "not-found",
      }))
    })
    return () => {
      ignore = true
    }
  }, [authStatus, params.id, days, query])

  const goBack = () => router.push(`/projects/${params.id}`)

  if (loading) {
    return (
      <div className="min-h-screen bg-background p-8">
        <div className="max-w-6xl mx-auto">
          <AnalyticsSkeleton />
        </div>
      </div>
    )
  }

  if (notFound) {
    return (
      <div className="min-h-screen bg-background p-8">
        <div className="max-w-6xl mx-auto">
          <Button variant="outline" onClick={goBack} className="mb-4">
            ← Back to Project
          </Button>
          <EmptyState
            icon={<HugeiconsIcon icon={Analytics01Icon} size={64} />}
            title="Project not found"
            description="This project doesn't exist or you don't have access to it."
          />
        </div>
      </div>
    )
  }

  const summary = analytics?.summary ?? { total_downloads: 0, total_plays: 0, total_listen_hours: 0 }
  const weeklyDownloads = analytics?.trends.weekly_downloads ?? []
  const topEpisodes = analytics?.top_episodes ?? []
  const isEmpty =
    summary.total_downloads === 0 &&
    summary.total_plays === 0 &&
    summary.total_listen_hours === 0 &&
    weeklyDownloads.length === 0
  const maxDownloads = Math.max(0, ...weeklyDownloads.map((w) => w.downloads))

  return (
    <div className="min-h-screen bg-background p-8">
      <div className="max-w-6xl mx-auto">
        <Button variant="outline" onClick={goBack} className="mb-4">
          ← Back to Project
        </Button>

        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">Analytics</h1>
          <Select value={days} onValueChange={setDays}>
            <SelectTrigger aria-label="Select time period" className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7 days</SelectItem>
              <SelectItem value="30">30 days</SelectItem>
              <SelectItem value="90">90 days</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {isEmpty ? (
          <EmptyState
            icon={<HugeiconsIcon icon={Analytics01Icon} size={64} />}
            title="No analytics yet"
            description="Data appears once episodes are downloaded or played"
          />
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base font-medium text-muted-foreground">
                    <HugeiconsIcon icon={Download01Icon} size={16} />
                    Total downloads
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-3xl font-bold">{summary.total_downloads}</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base font-medium text-muted-foreground">
                    <HugeiconsIcon icon={PlayIcon} size={16} />
                    Total plays
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-3xl font-bold">{summary.total_plays}</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base font-medium text-muted-foreground">
                    <HugeiconsIcon icon={MusicNote01Icon} size={16} />
                    Total listen hours
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-3xl font-bold">{summary.total_listen_hours}</p>
                </CardContent>
              </Card>
            </div>

            <Card className="mb-8">
              <CardHeader>
                <CardTitle>Weekly downloads</CardTitle>
              </CardHeader>
              <CardContent>
                {weeklyDownloads.length === 0 ? (
                  <p className="text-muted-foreground">No downloads in this period</p>
                ) : (
                  <div className="space-y-2">
                    {weeklyDownloads.map((w) => {
                      const pct = maxDownloads > 0 ? (w.downloads / maxDownloads) * 100 : 0
                      return (
                        <div key={w.week} className="flex items-center gap-3">
                          <span className="text-sm text-muted-foreground w-20 shrink-0">{w.week}</span>
                          <div className="flex-1 bg-muted rounded h-2">
                            <div
                              className="bg-primary rounded h-2"
                              style={{ width: `${pct}%` }}
                              data-testid={`bar-${w.week}`}
                            />
                          </div>
                          <span className="text-sm font-medium w-10 text-right shrink-0">{w.downloads}</span>
                        </div>
                      )
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Top episodes</CardTitle>
              </CardHeader>
              <CardContent>
                {topEpisodes.length === 0 ? (
                  <p className="text-muted-foreground">No episode downloads yet</p>
                ) : (
                  <ul className="space-y-2">
                    {topEpisodes.map((ep) => (
                      <li key={ep.episode_id} className="flex justify-between items-center">
                        <a
                          href={`/episodes/${ep.episode_id}`}
                          className="text-sm font-medium text-primary hover:underline"
                        >
                          {ep.episode_id}
                        </a>
                        <span className="text-sm text-muted-foreground">{ep.downloads} downloads</span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
  )
}
