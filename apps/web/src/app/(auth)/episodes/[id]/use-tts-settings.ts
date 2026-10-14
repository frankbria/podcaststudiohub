import { useState, type Dispatch, type SetStateAction } from "react"
import { showSuccessToast } from "@/lib/toast"
import { buildTtsConfig, createTtsConfig, putEpisodeTtsConfig } from "./episode-api"
import type { TTSConfig } from "./types"

// ElevenLabs ships with empty voice-ID defaults, so a saved config is only
// usable once the user provides real voice IDs (#221). Other providers have
// working defaults and need no extra input.
function isTtsConfigValid(name: string, provider: string, voice1Id: string, voice2Id: string) {
  if (name.trim() === "") return false
  return provider !== "elevenlabs" || (voice1Id.trim() !== "" && voice2Id.trim() !== "")
}

interface UseTtsSettingsArgs {
  episodeId: string
  setTtsConfigs: Dispatch<SetStateAction<TTSConfig[]>>
  selectedTtsConfigId: string
  setSelectedTtsConfigId: (id: string) => void
  loadEpisode: () => Promise<void>
}

/** State and actions behind the TTS Settings dialog. */
export function useTtsSettings({
  episodeId,
  setTtsConfigs,
  selectedTtsConfigId,
  setSelectedTtsConfigId,
  loadEpisode,
}: UseTtsSettingsArgs) {
  const [showTTSDialog, setShowTTSDialog] = useState(false)
  const [newTtsProvider, setNewTtsProvider] = useState<string>("openai")
  const [newTtsName, setNewTtsName] = useState<string>("")
  const [newTtsVoice1Id, setNewTtsVoice1Id] = useState<string>("")
  const [newTtsVoice2Id, setNewTtsVoice2Id] = useState<string>("")
  const [savingTts, setSavingTts] = useState(false)

  const canSave = isTtsConfigValid(newTtsName, newTtsProvider, newTtsVoice1Id, newTtsVoice2Id)

  const saveTTSConfig = async () => {
    if (!canSave) return
    setSavingTts(true)
    try {
      const config = buildTtsConfig(newTtsProvider, newTtsVoice1Id, newTtsVoice2Id)
      const newConfig = await createTtsConfig(newTtsName, newTtsProvider, config)
      if (!newConfig) return
      setTtsConfigs((prev) => [...prev, newConfig])
      setSelectedTtsConfigId(newConfig.id)
      setNewTtsName("")
      setNewTtsVoice1Id("")
      setNewTtsVoice2Id("")
      showSuccessToast("TTS configuration saved")
    } finally {
      setSavingTts(false)
    }
  }

  const applyTTSConfig = async () => {
    if (!(await putEpisodeTtsConfig(episodeId, selectedTtsConfigId))) return
    showSuccessToast("TTS settings applied")
    await loadEpisode()
    setShowTTSDialog(false)
  }

  return {
    showTTSDialog,
    setShowTTSDialog,
    newTtsProvider,
    setNewTtsProvider,
    newTtsName,
    setNewTtsName,
    newTtsVoice1Id,
    setNewTtsVoice1Id,
    newTtsVoice2Id,
    setNewTtsVoice2Id,
    savingTts,
    canSave,
    saveTTSConfig,
    applyTTSConfig,
  }
}
