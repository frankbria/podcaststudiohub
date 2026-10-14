"use client"

import type { ChangeEvent } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { TTS_DEFAULT_SENTINEL, type TTSConfig } from "./types"

function onValue(setter: (value: string) => void) {
  return function handleChange(event: ChangeEvent<HTMLInputElement>) {
    setter(event.target.value)
  }
}

function renderConfigOption(cfg: TTSConfig) {
  return (
    <SelectItem key={cfg.id} value={cfg.id}>
      {cfg.name} ({cfg.provider})
      {cfg.is_default ? " — default" : ""}
    </SelectItem>
  )
}

interface SavedConfigSelectProps {
  ttsConfigs: TTSConfig[]
  selectedTtsConfigId: string
  onSelect: (id: string) => void
}

function SavedConfigSelect({ ttsConfigs, selectedTtsConfigId, onSelect }: SavedConfigSelectProps) {
  if (ttsConfigs.length === 0) return null
  return (
    <div>
      <Label htmlFor="tts-config-select" className="mb-1">Saved Configurations</Label>
      <Select value={selectedTtsConfigId} onValueChange={onSelect}>
        <SelectTrigger id="tts-config-select" aria-label="Select a saved TTS configuration">
          <SelectValue placeholder="Select a configuration" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={TTS_DEFAULT_SENTINEL}>Default (no override)</SelectItem>
          {ttsConfigs.map(renderConfigOption)}
        </SelectContent>
      </Select>
    </div>
  )
}

interface ElevenLabsVoiceFieldsProps {
  voice1Id: string
  voice2Id: string
  onVoice1Change: (value: string) => void
  onVoice2Change: (value: string) => void
}

function ElevenLabsVoiceFields(props: ElevenLabsVoiceFieldsProps) {
  const { voice1Id, voice2Id, onVoice1Change, onVoice2Change } = props
  return (
    <>
      <div>
        <Label htmlFor="new-tts-voice-1" className="mb-1">Voice 1 ID</Label>
        <Input
          id="new-tts-voice-1"
          value={voice1Id}
          onChange={onValue(onVoice1Change)}
          placeholder="21m00Tcm4TlvDq8ikWAM"
          aria-required="true"
        />
      </div>
      <div>
        <Label htmlFor="new-tts-voice-2" className="mb-1">Voice 2 ID</Label>
        <Input
          id="new-tts-voice-2"
          value={voice2Id}
          onChange={onValue(onVoice2Change)}
          placeholder="AZnzlk1XvdvUeBnXmlld"
          aria-required="true"
        />
      </div>
      <p className="text-sm text-muted-foreground">
        Required ElevenLabs voice IDs from your ElevenLabs account (Voice Library).
      </p>
    </>
  )
}

export interface TtsSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  ttsConfigs: TTSConfig[]
  selectedTtsConfigId: string
  onSelectConfig: (id: string) => void
  name: string
  onNameChange: (value: string) => void
  provider: string
  onProviderChange: (value: string) => void
  voice1Id: string
  onVoice1Change: (value: string) => void
  voice2Id: string
  onVoice2Change: (value: string) => void
  saving: boolean
  canSave: boolean
  onSave: () => void
  onApply: () => void
}

export function TtsSettingsDialog(props: TtsSettingsDialogProps) {
  const { provider, voice1Id, voice2Id } = props
  const voiceFields =
    provider === "elevenlabs" ? (
      <ElevenLabsVoiceFields
        voice1Id={voice1Id}
        voice2Id={voice2Id}
        onVoice1Change={props.onVoice1Change}
        onVoice2Change={props.onVoice2Change}
      />
    ) : null

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>TTS Settings</DialogTitle>
          <DialogDescription>
            Select a text-to-speech provider for this episode
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 mt-4">
          <SavedConfigSelect
            ttsConfigs={props.ttsConfigs}
            selectedTtsConfigId={props.selectedTtsConfigId}
            onSelect={props.onSelectConfig}
          />

          <div className="border rounded p-3 space-y-3">
            <p className="text-sm font-medium">Create New Configuration</p>
            <div>
              <Label htmlFor="new-tts-name" className="mb-1">Name</Label>
              <Input
                id="new-tts-name"
                value={props.name}
                onChange={onValue(props.onNameChange)}
                placeholder="My ElevenLabs Config"
                aria-required="true"
              />
            </div>
            <div>
              <Label htmlFor="new-tts-provider" className="mb-1">Provider</Label>
              <Select value={provider} onValueChange={props.onProviderChange}>
                <SelectTrigger id="new-tts-provider" aria-label="Select TTS provider">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="openai">OpenAI</SelectItem>
                  <SelectItem value="elevenlabs">ElevenLabs</SelectItem>
                  <SelectItem value="gemini">Gemini</SelectItem>
                  <SelectItem value="gemini_multi">Gemini Multi-Speaker</SelectItem>
                  <SelectItem value="edge">Edge TTS (Free)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {voiceFields}
            <Button
              onClick={props.onSave}
              disabled={props.saving || !props.canSave}
              variant="outline"
              className="w-full"
            >
              {props.saving ? "Saving..." : "Save Configuration"}
            </Button>
          </div>

          <Button onClick={props.onApply} className="w-full">
            Apply to Episode
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
