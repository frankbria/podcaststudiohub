"use client"

import { useState } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { Download01Icon, Loading03Icon } from "@hugeicons/core-free-icons"
import { Button } from "@/components/ui/button"
import { downloadAudioFile, sanitizeFilename } from "@/lib/download"

export interface DownloadButtonProps {
  audioUrl: string | null | undefined
  episodeTitle: string
  isLoading?: boolean
  onDownloaded?: () => void
}

export function DownloadButton({
  audioUrl,
  episodeTitle,
  isLoading = false,
  onDownloaded,
}: DownloadButtonProps) {
  const [downloading, setDownloading] = useState(false)

  const handleDownload = async () => {
    if (!audioUrl) return

    setDownloading(true)
    try {
      const filename = sanitizeFilename(episodeTitle)
      await downloadAudioFile(audioUrl, filename)
      onDownloaded?.()
    } catch (error) {
      console.error("Download failed:", error)
    } finally {
      setDownloading(false)
    }
  }

  const isDisabled = !audioUrl || isLoading || downloading

  return (
    <Button
      onClick={handleDownload}
      disabled={isDisabled}
      variant="outline"
      size="sm"
      className="flex items-center gap-2"
      aria-label={downloading ? "Downloading..." : "Download MP3"}
    >
      <HugeiconsIcon
        icon={downloading ? Loading03Icon : Download01Icon}
        size={16}
      />
      {downloading ? "Downloading..." : "Download MP3"}
    </Button>
  )
}
