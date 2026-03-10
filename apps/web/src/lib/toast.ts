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

interface ResponseLike {
  status: number
  statusText: string
}

const isResponseLike = (error: unknown): error is ResponseLike =>
  error !== null &&
  typeof error === "object" &&
  "status" in error &&
  "statusText" in error

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
