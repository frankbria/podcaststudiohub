import { useState, type Dispatch, type SetStateAction } from "react"
import { useForm, useWatch } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { contentSourceSchema, type ContentSourceFormData } from "@/lib/validation"
import { submitContentSource, removeContentSource } from "./episode-api"
import type { ContentSource } from "./types"

interface UseContentSourcesArgs {
  episodeId: string
  setContentSources: Dispatch<SetStateAction<ContentSource[]>>
  loadContentSources: () => Promise<void>
}

/** The add-content form/dialog and the delete-confirmation flow for an episode's sources. */
export function useContentSources({
  episodeId,
  setContentSources,
  loadContentSources,
}: UseContentSourcesArgs) {
  const [showAddContentDialog, setShowAddContentDialog] = useState(false)
  const [deleteContentSource, setDeleteContentSource] = useState<ContentSource | null>(null)
  const [isDeletingContent, setIsDeletingContent] = useState(false)

  const form = useForm<ContentSourceFormData>({
    resolver: zodResolver(contentSourceSchema),
    mode: "onChange",
    defaultValues: {
      sourceType: "url",
    },
  })
  const { reset, control } = form
  const sourceType = useWatch({ control, name: "sourceType" })

  const onSubmitContent = async (data: ContentSourceFormData) => {
    if (!(await submitContentSource(episodeId, data))) return
    setShowAddContentDialog(false)
    reset()
    loadContentSources()
  }

  const handleDialogOpenChange = (open: boolean) => {
    setShowAddContentDialog(open)
    if (!open) {
      reset()
    }
  }

  const handleConfirmDeleteContent = async () => {
    if (!deleteContentSource) return
    setIsDeletingContent(true)
    try {
      if (!(await removeContentSource(deleteContentSource.id))) return
      setDeleteContentSource(null)
      setContentSources((prev) => prev.filter((s) => s.id !== deleteContentSource.id))
    } finally {
      setIsDeletingContent(false)
    }
  }

  return {
    form,
    sourceType,
    showAddContentDialog,
    setShowAddContentDialog,
    deleteContentSource,
    setDeleteContentSource,
    isDeletingContent,
    onSubmitContent,
    handleDialogOpenChange,
    handleConfirmDeleteContent,
  }
}
