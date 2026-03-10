"use client"

import { Toaster } from "sonner"

export function ToastProvider() {
  return (
    <Toaster
      position="top-right"
      richColors
      theme="light"
      expand={true}
      visibleToasts={3}
      closeButton={true}
    />
  )
}
