"use client"

import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { webhookDistributionSchema, type WebhookDistributionFormData } from "@/lib/validation"
import { showErrorToast } from "@/lib/toast"
import { extractApiErrorDetail } from "@/lib/api-error"
import { HugeiconsIcon } from "@hugeicons/react"
import { WebhookIcon } from "@hugeicons/core-free-icons"

interface WebhookConnectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConnected: () => void
}

export function WebhookConnectDialog({ open, onOpenChange, onConnected }: WebhookConnectDialogProps) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isValid },
    reset,
  } = useForm<WebhookDistributionFormData>({
    resolver: zodResolver(webhookDistributionSchema),
    mode: "onChange",
    defaultValues: { name: "", url: "", method: "POST" },
  })

  useEffect(() => {
    if (open) {
      reset({ name: "", url: "", method: "POST" })
    }
  }, [open, reset])

  const onSubmit = async (data: WebhookDistributionFormData) => {
    try {
      const response = await fetch("/api/proxy/distribution-targets/webhook", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: data.name.trim(),
          url: data.url.trim(),
          method: data.method,
        }),
      })

      if (response.ok) {
        reset()
        onConnected()
        onOpenChange(false)
      } else {
        // Surface the backend's validation message (e.g. the SSRF guard's 422
        // "Webhook URL is not allowed: ..." detail) when present.
        const body = await response.json().catch(() => null)
        showErrorToast(
          "Failed to connect webhook: " + extractApiErrorDetail(body, response.statusText)
        )
      }
    } catch (error) {
      console.error("Failed to connect webhook:", error)
      showErrorToast("Failed to connect webhook: Network error")
    }
  }

  const handleOpenChange = (nextOpen: boolean) => {
    onOpenChange(nextOpen)
    if (!nextOpen) {
      reset()
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <HugeiconsIcon icon={WebhookIcon} size={20} />
            Connect Webhook
          </DialogTitle>
          <DialogDescription>
            Send a notification to a custom HTTPS endpoint whenever an episode is published.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 mt-4" noValidate>
          <div>
            <Label htmlFor="webhook-name" className="mb-1">
              Name <span className="text-destructive">*</span>
            </Label>
            <Input
              id="webhook-name"
              type="text"
              placeholder="My webhook"
              aria-invalid={errors.name ? "true" : "false"}
              aria-describedby={errors.name ? "webhook-name-error" : undefined}
              {...register("name")}
              className={errors.name ? "border-destructive" : ""}
            />
            {errors.name && (
              <p id="webhook-name-error" className="text-destructive text-sm mt-1" role="alert">
                {errors.name.message}
              </p>
            )}
          </div>
          <div>
            <Label htmlFor="webhook-url" className="mb-1">
              URL <span className="text-destructive">*</span>
            </Label>
            <Input
              id="webhook-url"
              type="text"
              placeholder="https://example.com/webhook"
              aria-invalid={errors.url ? "true" : "false"}
              aria-describedby={errors.url ? "webhook-url-error" : undefined}
              {...register("url")}
              className={errors.url ? "border-destructive" : ""}
            />
            {errors.url && (
              <p id="webhook-url-error" className="text-destructive text-sm mt-1" role="alert">
                {errors.url.message}
              </p>
            )}
          </div>
          <div>
            <Label htmlFor="webhook-method" className="mb-1">
              Method
            </Label>
            <select
              id="webhook-method"
              {...register("method")}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <option value="POST">POST</option>
              <option value="GET">GET</option>
            </select>
          </div>
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting || !isValid}>
              {isSubmitting ? "Connecting..." : "Connect"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
