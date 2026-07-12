"use client"

import { useState, useEffect, useCallback } from "react"
import { useRouter, useParams } from "next/navigation"
import { useSession } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { CardSkeleton } from "@/components/skeletons/CardSkeleton"
import { EmptyState } from "@/components/empty-state/EmptyState"
import {
  EditPodcastMetadataDialog,
} from "@/components/dialogs/EditPodcastMetadataDialog"
import { showSuccessToast, showErrorToast } from "@/lib/toast"
import type { PodcastMetadataFormData } from "@/lib/validation"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  RssIcon,
  Copy01Icon,
  PencilEdit01Icon,
  Refresh01Icon,
} from "@hugeicons/core-free-icons"

interface RssFeed {
  id: string
  project_id: string
  tenant_id: string
  s3_key?: string | null
  public_url?: string | null
  validation_status?: Record<string, string> | null
  last_generated?: string | null
  created_at: string
  updated_at: string
}

interface ProjectSummary {
  id: string
  title: string
  podcastMetadata: Partial<PodcastMetadataFormData>
}

interface RawPodcastMetadata {
  show_title?: string
  author?: string
  description?: string
  category?: string
  language?: string
  explicit?: boolean
  copyright?: string
  artwork_url?: string
  website_url?: string
}

function mapPodcastMetadataToForm(
  raw: RawPodcastMetadata | undefined
): Partial<PodcastMetadataFormData> {
  if (!raw) return {}
  return {
    showTitle: raw.show_title ?? "",
    author: raw.author ?? "",
    description: raw.description ?? "",
    category: raw.category ?? "",
    language: raw.language ?? "",
    explicit: raw.explicit ?? false,
    copyright: raw.copyright ?? "",
    artworkUrl: raw.artwork_url ?? "",
    websiteUrl: raw.website_url ?? "",
  }
}

export default function DistributionPage() {
  const router = useRouter()
  const params = useParams()
  const { status: authStatus } = useSession()
  const [project, setProject] = useState<ProjectSummary | null>(null)
  const [feed, setFeed] = useState<RssFeed | null>(null)
  const [loading, setLoading] = useState(true)
  const [isGenerating, setIsGenerating] = useState(false)
  const [showEditMetadata, setShowEditMetadata] = useState(false)

  // Backend calls go through the same-origin /api/proxy handler, which injects
  // the bearer token server-side from the httpOnly cookie — no client token (#212).
  const loadProject = useCallback(async () => {
    try {
      const response = await fetch(`/api/proxy/projects/${params.id}`)
      if (response.ok) {
        const data = (await response.json()) as {
          id: string
          name: string
          podcast_metadata?: RawPodcastMetadata
        }
        setProject({
          id: data.id,
          title: data.name,
          podcastMetadata: mapPodcastMetadataToForm(data.podcast_metadata),
        })
      }
    } catch (error) {
      console.error("Failed to load project:", error)
    }
  }, [params.id])

  const loadFeed = useCallback(async () => {
    try {
      const response = await fetch(`/api/proxy/projects/${params.id}/rss-feed`)
      if (response.ok) {
        const data = (await response.json()) as RssFeed
        setFeed(data)
      } else if (response.status === 404) {
        setFeed(null)
      } else {
        setFeed(null)
        showErrorToast("Failed to load RSS feed")
      }
    } catch (error) {
      console.error("Failed to load RSS feed:", error)
      showErrorToast("Failed to load RSS feed: Network error")
    } finally {
      setLoading(false)
    }
  }, [params.id])

  useEffect(() => {
    if (authStatus === "authenticated") {
      loadProject()
      loadFeed()
    }
  }, [authStatus, loadProject, loadFeed])

  const handleGenerate = async () => {
    setIsGenerating(true)
    try {
      const response = await fetch(
        `/api/proxy/projects/${params.id}/rss-feed/generate`,
        { method: "POST" }
      )
      if (response.ok) {
        const data = (await response.json()) as RssFeed
        setFeed(data)
        showSuccessToast("RSS feed generated")
      } else if (response.status === 422) {
        const body = (await response.json()) as { detail: string }
        showErrorToast(`Failed to generate RSS feed: ${body.detail}`)
        setShowEditMetadata(true)
      } else if (response.status === 404) {
        showErrorToast("Project not found")
      } else {
        showErrorToast("Failed to generate RSS feed")
      }
    } catch (error) {
      console.error("Failed to generate RSS feed:", error)
      showErrorToast("Failed to generate RSS feed: Network error")
    } finally {
      setIsGenerating(false)
    }
  }

  const handleUpdateMetadata = async (data: PodcastMetadataFormData) => {
    const podcastMetadata: RawPodcastMetadata = {
      show_title: data.showTitle,
      author: data.author,
      description: data.description,
      explicit: data.explicit ?? false,
      ...(data.category ? { category: data.category } : {}),
      ...(data.language ? { language: data.language } : {}),
      ...(data.copyright ? { copyright: data.copyright } : {}),
      ...(data.artworkUrl ? { artwork_url: data.artworkUrl } : {}),
      ...(data.websiteUrl ? { website_url: data.websiteUrl } : {}),
    }

    try {
      const response = await fetch(`/api/proxy/projects/${params.id}/rss-feed`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ podcast_metadata: podcastMetadata }),
      })

      if (response.ok) {
        const feedData = (await response.json()) as RssFeed
        setFeed(feedData)
        setProject((prev) => (prev ? { ...prev, podcastMetadata: data } : prev))
        showSuccessToast("Podcast metadata updated")
        setShowEditMetadata(false)
      } else if (response.status === 422) {
        const body = (await response.json()) as { detail: string }
        showErrorToast(`Failed to update podcast metadata: ${body.detail}`)
      } else if (response.status === 404) {
        showErrorToast("Project not found")
      } else {
        showErrorToast("Failed to update podcast metadata")
      }
    } catch (error) {
      console.error("Failed to update podcast metadata:", error)
      showErrorToast("Failed to update podcast metadata: Network error")
    }
  }

  const handleCopyUrl = async () => {
    if (!feed?.public_url) return
    try {
      await navigator.clipboard.writeText(feed.public_url)
      showSuccessToast("Feed URL copied to clipboard")
    } catch (error) {
      console.error("Failed to copy feed URL:", error)
      showErrorToast("Failed to copy feed URL")
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background p-8">
        <div className="max-w-6xl mx-auto">
          <CardSkeleton />
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background p-8">
      <div className="max-w-6xl mx-auto">
        <Button
          variant="outline"
          onClick={() => router.push(`/projects/${params.id}`)}
          className="mb-4"
        >
          ← Back to Project
        </Button>

        <div className="mb-8">
          <h1 className="text-3xl font-bold">RSS Feed & Distribution</h1>
          <p className="text-muted-foreground mt-1">
            This feed URL is what Spotify and Apple Podcasts ingest to publish your show.
          </p>
        </div>

        {!feed ? (
          <EmptyState
            icon={<HugeiconsIcon icon={RssIcon} size={64} />}
            title="No RSS feed yet"
            description="Generate an RSS feed to start distributing this podcast"
            action={{
              label: "Generate RSS feed",
              onClick: handleGenerate,
            }}
          />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>Podcast RSS Feed</CardTitle>
              <CardDescription>
                {feed.last_generated
                  ? `Last generated: ${new Date(feed.last_generated).toLocaleString()}`
                  : "Not yet generated"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div>
                <p className="text-sm font-medium mb-1">Feed URL</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 truncate rounded bg-muted px-3 py-2 text-sm">
                    {feed.public_url ?? "Not available"}
                  </code>
                  <Button
                    variant="outline"
                    size="sm"
                    aria-label="Copy feed URL"
                    onClick={handleCopyUrl}
                    disabled={!feed.public_url}
                  >
                    <HugeiconsIcon icon={Copy01Icon} size={16} />
                  </Button>
                </div>
              </div>

              <div>
                <p className="text-sm font-medium mb-1">Validation status</p>
                {feed.validation_status && Object.keys(feed.validation_status).length > 0 ? (
                  <ul className="space-y-1">
                    {Object.entries(feed.validation_status).map(([platform, platformStatus]) => (
                      <li key={platform} className="flex items-center gap-2 text-sm">
                        <span className="capitalize">{platform}</span>
                        <span className="text-muted-foreground">{String(platformStatus)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground text-sm">Not yet validated</p>
                )}
              </div>

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={handleGenerate}
                  disabled={isGenerating}
                >
                  <HugeiconsIcon icon={Refresh01Icon} size={16} />
                  {isGenerating ? "Regenerating..." : "Regenerate feed"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setShowEditMetadata(true)}
                >
                  <HugeiconsIcon icon={PencilEdit01Icon} size={16} />
                  Edit podcast metadata
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        <EditPodcastMetadataDialog
          open={showEditMetadata}
          onOpenChange={setShowEditMetadata}
          initialMetadata={project?.podcastMetadata}
          onSubmitMetadata={handleUpdateMetadata}
        />
      </div>
    </div>
  )
}
