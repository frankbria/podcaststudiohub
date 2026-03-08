"use client"

import { useState } from "react"
import { Download } from "lucide-react"
import { Button } from "@/components/ui/button"
import { sanitizeFilename, downloadAudioFile } from "@/lib/download"

interface DownloadButtonProps {
  audioUrl: string | null | undefined
  episodeTitle: string
  isLoading?: boolean
}

export function DownloadButton({
  audioUrl,
  episodeTitle,
  isLoading = false,
}: DownloadButtonProps) {
  const [downloading, setDownloading] = useState(false)

  const handleDownload = async () => {
    if (!audioUrl) return

    setDownloading(true)
    try {
      const filename = `${sanitizeFilename(episodeTitle)}.mp3`
      await downloadAudioFile(audioUrl, filename)
    } catch (error) {
      console.error("Download failed:", error)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <Button
      onClick={handleDownload}
      disabled={!audioUrl || isLoading || downloading}
      variant="outline"
      className="flex items-center gap-2"
    >
      <Download className="h-4 w-4" />
      {downloading ? "Downloading..." : "Download MP3"}
    </Button>
  )
}
