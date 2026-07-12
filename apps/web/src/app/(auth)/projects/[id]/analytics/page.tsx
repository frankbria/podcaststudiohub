"use client"

import { useState, useEffect, useCallback } from "react"
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

export default function ProjectAnalyticsPage() {
  const router = useRouter()
  const params = useParams()
  const { status: authStatus } = useSession()
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState("30")

  // Backend calls go through the same-origin /api/proxy handler, which injects
  // the bearer token server-side from the httpOnly cookie — no client token (#212).
  const loadAnalytics = useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetch(
        `/api/proxy/projects/${params.id}/analytics?days=${days}`
      )
      if (response.ok) {
        const data = await response.json() as Analytics
        setAnalytics(data)
        setNotFound(false)
      } else if (response.status === 404) {
        setNotFound(true)
      } else {
        showErrorToast("Failed to load analytics")
      }
    } catch (error) {
      console.error("Failed to load analytics:", error)
      showErrorToast("Failed to load analytics: Network error")
    } finally {
      setLoading(false)
    }
  }, [params.id, days])

  useEffect(() => {
    if (authStatus === "authenticated") {
      loadAnalytics()
    }
  }, [authStatus, loadAnalytics])

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
