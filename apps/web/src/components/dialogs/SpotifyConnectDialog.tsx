"use client"

import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { showErrorToast } from "@/lib/toast"
import { HugeiconsIcon } from "@hugeicons/react"
import { SpotifyIcon } from "@hugeicons/core-free-icons"

interface SpotifyConnectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function SpotifyConnectDialog({ open, onOpenChange }: SpotifyConnectDialogProps) {
  const [isConnecting, setIsConnecting] = useState(false)

  const handleConnect = async () => {
    setIsConnecting(true)
    try {
      const response = await fetch("/api/proxy/distribution-targets/spotify/authorize", {
        method: "POST",
      })

      if (response.ok) {
        const data = (await response.json()) as { authorize_url: string; state: string }
        // Full-page redirect: the proxy strips cross-origin redirects, so the
        // authorize_url cannot be fetched — the browser must navigate to it.
        // The backend callback's redirect URL must point back to /distribution
        // (env-configured follow-up).
        window.location.assign(data.authorize_url)
      } else if (response.status === 503) {
        showErrorToast("Spotify OAuth is not configured on the server")
      } else {
        showErrorToast("Failed to start Spotify connection: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to start Spotify connection:", error)
      showErrorToast("Failed to start Spotify connection: Network error")
    } finally {
      setIsConnecting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <HugeiconsIcon icon={SpotifyIcon} size={20} />
            Connect Spotify
          </DialogTitle>
          <DialogDescription>
            Authorize Podcastfy Studio Hub to distribute episodes to Spotify for Podcasters.
          </DialogDescription>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Spotify ingests episodes from your project&apos;s public RSS feed — generate the feed
          from a project&apos;s Distribution page. Connecting your account here records a
          distribution target; it does not directly upload episodes.
        </p>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isConnecting}
          >
            Cancel
          </Button>
          <Button type="button" onClick={handleConnect} disabled={isConnecting}>
            {isConnecting ? "Connecting..." : "Connect Spotify"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
