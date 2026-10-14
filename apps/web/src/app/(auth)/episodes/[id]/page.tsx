"use client"

import type { ReactNode } from "react"
import { useRouter, useParams } from "next/navigation"
import { useSession } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { AudioPlayerSkeleton } from "@/components/skeletons/AudioPlayerSkeleton"
import { EmptyState } from "@/components/empty-state/EmptyState"
import { HugeiconsIcon } from "@hugeicons/react"
import { Alert02Icon } from "@hugeicons/core-free-icons"
import { AddContentDialog } from "./AddContentDialog"
import { AnalyticsCard } from "./AnalyticsCard"
import { ContentSourcesCard, DeleteContentSourceDialog } from "./ContentSourcesCard"
import { EpisodeHeaderCard } from "./EpisodeHeaderCard"
import { TtsSettingsDialog } from "./TtsSettingsDialog"
import { useContentSources } from "./use-content-sources"
import { useEpisode } from "./use-episode"
import { useEngagementTracking, useGeneratePodcast } from "./use-episode-actions"
import { useGenerationProgress } from "./use-generation-progress"
import { useTtsSettings } from "./use-tts-settings"
import type { ContentSource, Episode } from "./types"

// The App Router reuses this page's instance when only [id] changes, so its
// state (loading flag, loaded episode) would carry over and show the previous
// episode until the new fetch lands. Keying on the id remounts it instead (#529).
export default function EpisodePageRoute() {
  const params = useParams<{ id: string }>()
  return <EpisodePage key={params.id} />
}

function PageShell({ children }: { children: ReactNode }) {
  const content = children
  return (
    <div className="min-h-screen bg-background p-8">
      <div className="max-w-4xl mx-auto">{content}</div>
    </div>
  )
}

function EpisodeNotFound({ onBack }: { onBack: () => void }) {
  const action = { label: "Back", onClick: onBack }
  return (
    <EmptyState
      icon={<HugeiconsIcon icon={Alert02Icon} size={64} />}
      title="Episode not found"
      description="This episode could not be loaded. Please try again."
      action={action}
    />
  )
}

function canGenerate(contentSources: ContentSource[], episode: Episode): boolean {
  return contentSources.length > 0 && episode.generation_status === "draft"
}

interface GenerateButtonProps {
  enabled: boolean
  generating: boolean
  onGenerate: () => void
}

function GenerateButton({ enabled, generating, onGenerate }: GenerateButtonProps) {
  const label = generating ? "Starting Generation..." : "Generate Podcast"
  return (
    <Button
      onClick={onGenerate}
      disabled={!enabled || generating}
      className="w-full"
      size="lg"
    >
      {label}
    </Button>
  )
}

function EpisodePage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const { status: authStatus } = useSession()
  const data = useEpisode(params.id, authStatus)
  const { episode, loadEpisode, setProgress } = data
  const connectionStatus = useGenerationProgress({
    episodeId: params.id,
    status: episode?.generation_status,
    isMountedRef: data.isMountedRef,
    loadEpisode,
    setEpisode: data.setEpisode,
    setProgress,
    setProgressMessage: data.setProgressMessage,
  })
  const content = useContentSources({
    episodeId: params.id,
    setContentSources: data.setContentSources,
    loadContentSources: data.loadContentSources,
  })
  const tts = useTtsSettings({
    episodeId: params.id,
    setTtsConfigs: data.setTtsConfigs,
    selectedTtsConfigId: data.selectedTtsConfigId,
    setSelectedTtsConfigId: data.setSelectedTtsConfigId,
    loadEpisode,
  })
  const { generating, generatePodcast } = useGeneratePodcast({
    episodeId: params.id,
    setProgress,
    loadEpisode,
  })
  const { handleAudioPlay, handleDownloaded } = useEngagementTracking(episode, params.id)

  const goBack = () => router.back()

  if (data.loading) {
    return (
      <PageShell>
        <AudioPlayerSkeleton />
      </PageShell>
    )
  }

  if (!episode) {
    return (
      <PageShell>
        <EpisodeNotFound onBack={goBack} />
      </PageShell>
    )
  }

  const openTtsSettings = () => tts.setShowTTSDialog(true)
  const openAddContent = () => content.setShowAddContentDialog(true)
  const closeDeleteDialog = () => content.setDeleteContentSource(null)
  const backToProject = () => router.push(`/projects/${episode.project_id}`)

  return (
    <PageShell>
      <Button variant="outline" onClick={backToProject} className="mb-4">
        ← Back to Project
      </Button>

      <EpisodeHeaderCard
        episode={episode}
        progress={data.progress}
        progressMessage={data.progressMessage}
        connectionStatus={connectionStatus}
        generating={generating}
        onOpenTtsSettings={openTtsSettings}
        onApproved={data.applyEpisode}
        onPlay={handleAudioPlay}
        onDownloaded={handleDownloaded}
      />

      <AnalyticsCard
        analytics={data.analytics}
        loading={data.analyticsLoading}
        error={data.analyticsError}
      />

      <ContentSourcesCard
        contentSources={data.contentSources}
        onAdd={openAddContent}
        onDelete={content.setDeleteContentSource}
      />

      <GenerateButton
        enabled={canGenerate(data.contentSources, episode)}
        generating={generating}
        onGenerate={generatePodcast}
      />

      <AddContentDialog
        open={content.showAddContentDialog}
        onOpenChange={content.handleDialogOpenChange}
        form={content.form}
        sourceType={content.sourceType}
        onSubmit={content.onSubmitContent}
      />

      <TtsSettingsDialog
        open={tts.showTTSDialog}
        onOpenChange={tts.setShowTTSDialog}
        ttsConfigs={data.ttsConfigs}
        selectedTtsConfigId={data.selectedTtsConfigId}
        onSelectConfig={data.setSelectedTtsConfigId}
        name={tts.newTtsName}
        onNameChange={tts.setNewTtsName}
        provider={tts.newTtsProvider}
        onProviderChange={tts.setNewTtsProvider}
        voice1Id={tts.newTtsVoice1Id}
        onVoice1Change={tts.setNewTtsVoice1Id}
        voice2Id={tts.newTtsVoice2Id}
        onVoice2Change={tts.setNewTtsVoice2Id}
        saving={tts.savingTts}
        canSave={tts.canSave}
        onSave={tts.saveTTSConfig}
        onApply={tts.applyTTSConfig}
      />

      <DeleteContentSourceDialog
        source={content.deleteContentSource}
        isLoading={content.isDeletingContent}
        onClose={closeDeleteDialog}
        onConfirm={content.handleConfirmDeleteContent}
      />
    </PageShell>
  )
}
