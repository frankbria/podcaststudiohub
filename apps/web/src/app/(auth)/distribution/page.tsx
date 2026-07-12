"use client"

import { useState, useEffect, useCallback } from "react"
import { useSession } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { showSuccessToast, showErrorToast } from "@/lib/toast"
import { DistributionSkeleton } from "@/components/skeletons/DistributionSkeleton"
import { EmptyState } from "@/components/empty-state/EmptyState"
import { ConfirmDeleteDialog } from "@/components/dialogs/ConfirmDeleteDialog"
import { SpotifyConnectDialog } from "@/components/dialogs/SpotifyConnectDialog"
import { AppleConnectDialog } from "@/components/dialogs/AppleConnectDialog"
import { WebhookConnectDialog } from "@/components/dialogs/WebhookConnectDialog"
import type { DistributionTarget, DistributionTargetListResponse } from "@/lib/types/distribution"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  SpotifyIcon,
  AppleIcon,
  WebhookIcon,
  RssIcon,
  Refresh01Icon,
  Delete02Icon,
  PodcastIcon,
} from "@hugeicons/core-free-icons"

function targetTypeLabel(type: DistributionTarget["target_type"]): string {
  switch (type) {
    case "spotify":
      return "Spotify"
    case "apple_podcasts":
      return "Apple Podcasts"
    case "webhook":
      return "Webhook"
    default:
      return type
  }
}

function platformLabel(target: DistributionTarget): string {
  return target.platform_name || targetTypeLabel(target.target_type)
}

export default function DistributionPage() {
  const { status: authStatus } = useSession()
  const [targets, setTargets] = useState<DistributionTarget[]>([])
  const [loading, setLoading] = useState(true)
  const [showSpotifyDialog, setShowSpotifyDialog] = useState(false)
  const [showAppleDialog, setShowAppleDialog] = useState(false)
  const [showWebhookDialog, setShowWebhookDialog] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<DistributionTarget | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [togglingId, setTogglingId] = useState<string | null>(null)
  const [refreshingId, setRefreshingId] = useState<string | null>(null)

  // Backend calls go through the same-origin /api/proxy handler, which injects
  // the bearer token server-side from the httpOnly cookie — no client token (#212).
  const loadTargets = useCallback(async () => {
    try {
      const response = await fetch("/api/proxy/distribution-targets")
      if (response.ok) {
        const data = (await response.json()) as DistributionTargetListResponse
        setTargets(data.targets ?? [])
      } else {
        showErrorToast("Failed to load distribution targets")
      }
    } catch (error) {
      console.error("Failed to load distribution targets:", error)
      showErrorToast("Failed to load distribution targets: Network error")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (authStatus === "authenticated") {
      loadTargets()
    }
  }, [authStatus, loadTargets])

  // Spotify OAuth return: the backend callback redirects here with success/error
  // query params. We read window.location.search directly (not useSearchParams,
  // which forces a Suspense boundary at build time). The backend callback's
  // redirect URL must point back to /distribution (env-configured follow-up).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const success = params.get("success")
    const error = params.get("error")
    if (success === null && error === null) return

    if (error) {
      showErrorToast(error)
    } else {
      showSuccessToast(success || "Spotify connected")
    }
    window.history.replaceState({}, "", window.location.pathname)
    loadTargets()
    // Runs once on mount to consume the OAuth redirect's query params.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleTest = async (target: DistributionTarget) => {
    setTestingId(target.id)
    try {
      const response = await fetch(`/api/proxy/distribution-targets/${target.id}/test`, {
        method: "POST",
      })
      if (response.ok) {
        const data = (await response.json()) as { success: boolean; message: string }
        if (data.success) {
          showSuccessToast(data.message)
        } else {
          showErrorToast(data.message)
        }
      } else {
        showErrorToast("Failed to test connection: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to test connection:", error)
      showErrorToast("Failed to test connection: Network error")
    } finally {
      setTestingId(null)
    }
  }

  const handleToggleActive = async (target: DistributionTarget) => {
    setTogglingId(target.id)
    try {
      const response = await fetch(`/api/proxy/distribution-targets/${target.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !target.is_active }),
      })
      if (response.ok) {
        const updated = (await response.json()) as DistributionTarget
        setTargets((prev) => prev.map((t) => (t.id === updated.id ? updated : t)))
        showSuccessToast(updated.is_active ? "Target activated" : "Target deactivated")
      } else {
        showErrorToast("Failed to update target: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to update target:", error)
      showErrorToast("Failed to update target: Network error")
    } finally {
      setTogglingId(null)
    }
  }

  const handleRefreshToken = async (target: DistributionTarget) => {
    setRefreshingId(target.id)
    try {
      const response = await fetch(`/api/proxy/distribution-targets/${target.id}/refresh-token`, {
        method: "POST",
      })
      if (response.ok) {
        const updated = (await response.json()) as DistributionTarget
        setTargets((prev) => prev.map((t) => (t.id === updated.id ? updated : t)))
        showSuccessToast("Token refreshed")
      } else {
        showErrorToast("Failed to refresh token: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to refresh token:", error)
      showErrorToast("Failed to refresh token: Network error")
    } finally {
      setRefreshingId(null)
    }
  }

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      const response = await fetch(`/api/proxy/distribution-targets/${deleteTarget.id}`, {
        method: "DELETE",
      })
      if (response.ok) {
        showSuccessToast("Distribution target deleted")
        setTargets((prev) => prev.filter((t) => t.id !== deleteTarget.id))
        setDeleteTarget(null)
      } else {
        showErrorToast("Failed to delete target: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to delete target:", error)
      showErrorToast("Failed to delete target: Network error")
    } finally {
      setIsDeleting(false)
    }
  }

  const handleAppleConnected = () => {
    showSuccessToast("Apple Podcasts connected")
    loadTargets()
  }

  const handleWebhookConnected = () => {
    showSuccessToast("Webhook connected")
    loadTargets()
  }

  if (loading) {
    return <DistributionSkeleton />
  }

  return (
    <div className="min-h-screen bg-background p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-wrap justify-between items-center gap-4 mb-6">
          <h1 className="text-3xl font-bold">Distribution</h1>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => setShowSpotifyDialog(true)}>
              <HugeiconsIcon icon={SpotifyIcon} size={16} />
              Connect Spotify
            </Button>
            <Button variant="outline" onClick={() => setShowAppleDialog(true)}>
              <HugeiconsIcon icon={AppleIcon} size={16} />
              Connect Apple Podcasts
            </Button>
            <Button variant="outline" onClick={() => setShowWebhookDialog(true)}>
              <HugeiconsIcon icon={WebhookIcon} size={16} />
              Connect Webhook
            </Button>
          </div>
        </div>

        <Card className="mb-8 bg-muted/50">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <HugeiconsIcon icon={RssIcon} size={18} />
              How distribution works
            </CardTitle>
            <CardDescription>
              Spotify and Apple Podcasts ingest episodes via each project&apos;s public RSS
              feed — generate the feed from a project&apos;s Distribution page. Connecting an
              account here records a distribution target; it does not directly upload episodes.
            </CardDescription>
          </CardHeader>
        </Card>

        {targets.length === 0 ? (
          <EmptyState
            icon={<HugeiconsIcon icon={PodcastIcon} size={64} />}
            title="No platforms connected"
            description="Connect Spotify, Apple Podcasts, or a webhook to start distributing your episodes."
            action={{
              label: "Connect Spotify",
              onClick: () => setShowSpotifyDialog(true),
            }}
          />
        ) : (
          <div className="space-y-4">
            {targets.map((target) => {
              const label = platformLabel(target)
              const tokenValid = target.target_type === "spotify" ? !!target.token_valid : null
              return (
                <Card key={target.id}>
                  <CardHeader>
                    <div className="flex justify-between items-start gap-2">
                      <div>
                        <CardTitle>{label}</CardTitle>
                        <CardDescription>{targetTypeLabel(target.target_type)}</CardDescription>
                      </div>
                      <div className="flex gap-2 items-center">
                        <Badge variant={target.is_active ? "default" : "secondary"}>
                          {target.is_active ? "Active" : "Inactive"}
                        </Badge>
                        {target.target_type === "spotify" && (
                          <Badge
                            variant={tokenValid ? "default" : "outline"}
                            className={tokenValid ? "" : "bg-destructive/20 text-destructive border-transparent"}
                          >
                            {tokenValid ? "Token valid" : "Token expired"}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {target.target_type === "spotify" && target.token_expires_at && (
                      <p className="text-sm text-muted-foreground">
                        Token expires: {new Date(target.token_expires_at).toLocaleString()}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        aria-label={`Test ${label} connection`}
                        onClick={() => handleTest(target)}
                        disabled={testingId === target.id}
                      >
                        {testingId === target.id ? "Testing..." : "Test connection"}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        aria-label={`${target.is_active ? "Deactivate" : "Activate"} ${label}`}
                        onClick={() => handleToggleActive(target)}
                        disabled={togglingId === target.id}
                      >
                        {togglingId === target.id
                          ? "Updating..."
                          : target.is_active
                            ? "Deactivate"
                            : "Activate"}
                      </Button>
                      {target.target_type === "spotify" && (
                        <Button
                          variant="outline"
                          size="sm"
                          aria-label={`Refresh ${label} token`}
                          onClick={() => handleRefreshToken(target)}
                          disabled={refreshingId === target.id}
                        >
                          <HugeiconsIcon icon={Refresh01Icon} size={16} />
                          {refreshingId === target.id ? "Refreshing..." : "Refresh token"}
                        </Button>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        aria-label={`Delete ${label}`}
                        onClick={() => setDeleteTarget(target)}
                      >
                        <HugeiconsIcon icon={Delete02Icon} size={16} />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        )}

        <SpotifyConnectDialog open={showSpotifyDialog} onOpenChange={setShowSpotifyDialog} />
        <AppleConnectDialog
          open={showAppleDialog}
          onOpenChange={setShowAppleDialog}
          onConnected={handleAppleConnected}
        />
        <WebhookConnectDialog
          open={showWebhookDialog}
          onOpenChange={setShowWebhookDialog}
          onConnected={handleWebhookConnected}
        />

        {deleteTarget && (
          <ConfirmDeleteDialog
            open={!!deleteTarget}
            onOpenChange={(open) => {
              if (!open) setDeleteTarget(null)
            }}
            title="Delete distribution target?"
            description="This will stop distributing episodes to this platform."
            entityName={platformLabel(deleteTarget)}
            isLoading={isDeleting}
            onConfirm={handleConfirmDelete}
          />
        )}
      </div>
    </div>
  )
}
