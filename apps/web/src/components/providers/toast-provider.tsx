"use client"

import { Toaster } from "sonner"
import { useTheme } from "@/components/providers/theme-provider"

export function ToastProvider() {
  const { resolvedTheme } = useTheme()
  return (
    <Toaster
      position="top-right"
      richColors
      theme={resolvedTheme}
      expand={true}
      visibleToasts={3}
      closeButton={true}
    />
  )
}
