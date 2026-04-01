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
 * Async operation wrapper with automatic loading/success/error toasts.
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
