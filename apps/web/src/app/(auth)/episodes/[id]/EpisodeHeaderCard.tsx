"use client"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { DownloadButton } from "@/components/DownloadButton"
import type { ConnectionStatus } from "@/lib/event-source-manager"
import { ContentReviewNotice } from "./ContentReviewNotice"
import { STATUS_MESSAGES, isActiveStatus, type Episode } from "./types"

const STATUS_COLORS: Record<string, string> = {
  draft: "text-muted-foreground",
  queued: "text-primary",
  extracting: "text-accent-foreground",
  generating: "text-accent-foreground",
  synthesizing: "text-accent-foreground",
  composing: "text-accent-foreground",
  uploading: "text-accent-foreground",
  distributing: "text-accent-foreground",
  distribution_failed: "text-destructive",
  complete: "text-foreground",
  failed: "text-destructive",
}

function getStatusColor(status: string): string {
  return STATUS_COLORS[status] ?? STATUS_COLORS.draft
}

const CONNECTION_STATUS_CONFIG: Record<
  ConnectionStatus,
  { indicator: string; text: string; className: string }
> = {
  connecting: { indicator: "●", text: "Connecting...", className: "text-primary" },
  connected: { indicator: "●", text: "Connected", className: "text-foreground" },
  reconnecting: { indicator: "●", text: "Reconnecting...", className: "text-accent-foreground" },
  error: { indicator: "●", text: "Connection lost, retrying...", className: "text-destructive" },
  polling: { indicator: "●", text: "Using polling mode", className: "text-accent-foreground" },
  complete: { indicator: "●", text: "Generation complete", className: "text-foreground" },
}

interface ProgressConnectionStatusProps {
  status: ConnectionStatus
}

function ProgressConnectionStatus({ status }: ProgressConnectionStatusProps) {
  const config = CONNECTION_STATUS_CONFIG[status]
  if (!config) return null

  return (
    <p className={`text-xs mt-1 flex items-center gap-1 ${config.className}`}>
      <span aria-hidden="true">{config.indicator}</span>
      {config.text}
    </p>
  )
}

function progressText(progressMessage: string, status: string, progress: number): string {
  return progressMessage || STATUS_MESSAGES[status] || `${progress}% complete`
}

interface GenerationProgressBarProps {
  status: string
  progress: number
  progressMessage: string
  connectionStatus: ConnectionStatus
}

function GenerationProgressBar(props: GenerationProgressBarProps) {
  const { status, progress, progressMessage, connectionStatus } = props
  const text = progressText(progressMessage, status, progress)
  return (
    <div className="mb-4">
      <div
        role="progressbar"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Generation progress"
        className="w-full bg-muted rounded-full h-2.5"
      >
        <div
          className="bg-primary h-2.5 rounded-full transition-all"
          style={{ width: `${progress}%` }}
        ></div>
      </div>
      <p className="text-sm text-muted-foreground mt-1" aria-live="polite">
        {text}
      </p>
      <ProgressConnectionStatus status={connectionStatus} />
    </div>
  )
}

interface FailureMessageProps {
  episode: Episode
}

function FailureMessage({ episode }: FailureMessageProps) {
  const failed = episode.generation_status === "failed"
  const message = failed ? episode.generation_progress?.error_message : undefined
  if (!message) return null
  return <p className="text-sm text-destructive mb-4">Error: {message}</p>
}

function episodeStatus(episode: Episode): string {
  return episode.generation_status ?? "draft"
}

function titleOf(episode: Episode): string {
  return episode.episode_metadata?.title ?? "Episode"
}

interface EpisodeAudioProps {
  audioUrl: string
  episodeTitle: string
  generating: boolean
  onPlay: () => void
  onDownloaded: () => void
}

function EpisodeAudio(props: EpisodeAudioProps) {
  const { audioUrl, episodeTitle, generating, onPlay, onDownloaded } = props
  return (
    <div className="mt-4 space-y-2">
      <audio
        controls
        className="w-full"
        aria-label={`Podcast audio: ${episodeTitle}`}
        onPlay={onPlay}
      >
        <source src={audioUrl} type="audio/mpeg" />
      </audio>
      <DownloadButton
        audioUrl={audioUrl}
        episodeTitle={episodeTitle}
        isLoading={generating}
        onDownloaded={onDownloaded}
      />
    </div>
  )
}

interface EpisodeHeaderCardProps {
  episode: Episode
  progress: number
  progressMessage: string
  connectionStatus: ConnectionStatus
  generating: boolean
  onOpenTtsSettings: () => void
  onApproved: (episode: Episode) => void
  onPlay: () => void
  onDownloaded: () => void
}

export function EpisodeHeaderCard(props: EpisodeHeaderCardProps) {
  const { episode, progress, progressMessage, connectionStatus, generating } = props
  const status = episodeStatus(episode)
  const episodeTitle = titleOf(episode)
  const audioUrl = episode.s3_url

  return (
    <Card className="mb-6">
      <CardHeader>
        <div className="flex justify-between items-center">
          <div>
            <CardTitle>{episodeTitle}</CardTitle>
            <CardDescription>
              Status:{" "}
              <span className={getStatusColor(status)}>{status}</span>
            </CardDescription>
          </div>
          <Button variant="outline" onClick={props.onOpenTtsSettings} size="sm">
            TTS Settings
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isActiveStatus(episode.generation_status) && (
          <GenerationProgressBar
            status={episode.generation_status}
            progress={progress}
            progressMessage={progressMessage}
            connectionStatus={connectionStatus}
          />
        )}

        <FailureMessage episode={episode} />

        <ContentReviewNotice
          key={episode.id}
          episode={episode}
          onApproved={props.onApproved}
        />

        {audioUrl && (
          <EpisodeAudio
            audioUrl={audioUrl}
            episodeTitle={episodeTitle}
            generating={generating}
            onPlay={props.onPlay}
            onDownloaded={props.onDownloaded}
          />
        )}
      </CardContent>
    </Card>
  )
}
