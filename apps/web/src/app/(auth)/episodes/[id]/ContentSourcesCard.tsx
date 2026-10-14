"use client"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { EmptyState } from "@/components/empty-state/EmptyState"
import { ConfirmDeleteDialog } from "@/components/dialogs/ConfirmDeleteDialog"
import { HugeiconsIcon } from "@hugeicons/react"
import { FileEditIcon, Delete02Icon } from "@hugeicons/core-free-icons"
import type { ContentSource } from "./types"

interface SourcePreviewProps {
  source: ContentSource
}

function SourcePreview({ source }: SourcePreviewProps) {
  if (source.source_type === "url") {
    return <p className="text-sm text-muted-foreground">{source.source_data.url}</p>
  }
  if (source.source_type !== "text") return null
  return (
    <p className="text-sm text-muted-foreground">
      {source.source_data.content?.substring(0, 100)}...
    </p>
  )
}

interface ContentSourceItemProps {
  source: ContentSource
  onDelete: (source: ContentSource) => void
}

function ContentSourceItem({ source, onDelete }: ContentSourceItemProps) {
  const requestDelete = () => onDelete(source)
  return (
    <li className="flex items-center justify-between p-3 bg-muted rounded">
      <div>
        <span className="font-medium">{source.source_type}</span>
        {source.extraction_status && (
          <span className="ml-2 text-xs text-muted-foreground">
            ({source.extraction_status})
          </span>
        )}
        <SourcePreview source={source} />
      </div>
      <Button
        variant="ghost"
        size="sm"
        aria-label="Delete content source"
        onClick={requestDelete}
      >
        <HugeiconsIcon icon={Delete02Icon} size={16} />
      </Button>
    </li>
  )
}

interface ContentSourcesCardProps {
  contentSources: ContentSource[]
  onAdd: () => void
  onDelete: (source: ContentSource) => void
}

export function ContentSourcesCard({ contentSources, onAdd, onDelete }: ContentSourcesCardProps) {
  const renderSource = (source: ContentSource) => (
    <ContentSourceItem key={source.id} source={source} onDelete={onDelete} />
  )

  return (
    <Card className="mb-6">
      <CardHeader>
        <div className="flex justify-between items-center">
          <CardTitle>Content Sources</CardTitle>
          <Button onClick={onAdd}>Add Content</Button>
        </div>
      </CardHeader>
      <CardContent>
        {contentSources.length === 0 ? (
          <EmptyState
            icon={<HugeiconsIcon icon={FileEditIcon} size={48} />}
            title="No content added yet"
            description="Add a URL or text content to generate your podcast"
            action={{
              label: "Add Content",
              onClick: onAdd,
            }}
          />
        ) : (
          <ul className="space-y-2" aria-label="Content sources">
            {contentSources.map(renderSource)}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function deleteEntityName(source: ContentSource): string {
  if (source.source_type !== "url") return "text content"
  return source.source_data.url ?? "content source"
}

interface DeleteContentSourceDialogProps {
  source: ContentSource | null
  isLoading: boolean
  onClose: () => void
  onConfirm: () => Promise<void>
}

export function DeleteContentSourceDialog(props: DeleteContentSourceDialogProps) {
  const { source, isLoading, onClose, onConfirm } = props
  if (!source) return null

  const onOpenChange = (open: boolean) => {
    if (!open) onClose()
  }

  return (
    <ConfirmDeleteDialog
      open
      onOpenChange={onOpenChange}
      title="Delete Content Source?"
      description="This will permanently remove this content source from the episode."
      entityName={deleteEntityName(source)}
      isLoading={isLoading}
      onConfirm={onConfirm}
    />
  )
}
