/**
 * Toast utility functions for user feedback notifications.
 * Wraps sonner toast library with convenience helpers.
 */

import { toast } from "sonner"

export const showSuccessToast = (message: string) => {
  toast.success(message)
}

export const showErrorToast = (message: string) => {
  toast.error(message)
}

export const showLoadingToast = (message: string): string | number => {
  return toast.loading(message)
}

export const dismissToast = (toastId: string | number) => {
  toast.dismiss(toastId)
}

/**
 * Wraps an async operation with automatic loading/success/error toasts.
 * Returns the result on success, or null on failure.
 */
export const executeWithToast = async <T,>(
  operation: () => Promise<T>,
  successMessage: string,
  errorMessage?: string
): Promise<T | null> => {
  const loadingToastId = toast.loading("Loading...")

  try {
    const result = await operation()
    toast.dismiss(loadingToastId)
    toast.success(successMessage)
    return result
  } catch (error) {
    toast.dismiss(loadingToastId)
    const message = errorMessage || "Something went wrong"
    toast.error(message)
    console.error(message, error)
    return null
  }
}

/**
 * Checks if an unknown value looks like a fetch Response object.
 */
const isResponseLike = (
  error: unknown
): error is { status: number; statusText: string } =>
  typeof error === "object" &&
  error !== null &&
  "status" in error &&
  "statusText" in error

/**
 * Extracts a human-readable error message from various error types.
 */
export const extractErrorMessage = (error: unknown): string => {
  if (isResponseLike(error)) {
    if (error.status === 400) return "Invalid request. Please check your input."
    if (error.status === 401) return "You are not authorized. Please log in."
    if (error.status === 403) return "You don't have permission for this action."
    if (error.status === 404) return "Resource not found."
    if (error.status === 409) return "This resource already exists."
    if (error.status === 500) return "Server error. Please try again later."
    return `Error: ${error.statusText}`
  }

  if (error instanceof TypeError && error.message.includes("fetch")) {
    return "Network connection failed. Please check your internet."
  }

  if (error instanceof Error) {
    return error.message
  }

  return "An unexpected error occurred"
}
