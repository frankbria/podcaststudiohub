import {
  showSuccessToast,
  showErrorToast,
  showLoadingToast,
  dismissToast,
  executeWithToast,
  extractErrorMessage,
} from "@/lib/toast"

// Mock sonner
jest.mock("sonner", () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    loading: jest.fn().mockReturnValue(1),
    dismiss: jest.fn(),
  },
}))

import { toast } from "sonner"

describe("Toast utilities", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe("showSuccessToast", () => {
    it("calls toast.success with the provided message", () => {
      showSuccessToast("Project created successfully")
      expect(toast.success).toHaveBeenCalledWith("Project created successfully")
    })
  })

  describe("showErrorToast", () => {
    it("calls toast.error with the provided message", () => {
      showErrorToast("Failed to create project")
      expect(toast.error).toHaveBeenCalledWith("Failed to create project")
    })
  })

  describe("showLoadingToast", () => {
    it("calls toast.loading with the provided message and returns an id", () => {
      const id = showLoadingToast("Loading...")
      expect(toast.loading).toHaveBeenCalledWith("Loading...")
      expect(id).toBe(1)
    })
  })

  describe("dismissToast", () => {
    it("calls toast.dismiss with the provided id", () => {
      dismissToast(42)
      expect(toast.dismiss).toHaveBeenCalledWith(42)
    })

    it("accepts string ids", () => {
      dismissToast("some-id")
      expect(toast.dismiss).toHaveBeenCalledWith("some-id")
    })
  })

  describe("executeWithToast", () => {
    it("shows loading, then success toast on successful operation", async () => {
      const operation = jest.fn().mockResolvedValue({ id: 1 })
      const result = await executeWithToast(operation, "Done!")

      expect(toast.loading).toHaveBeenCalledWith("Loading...")
      expect(toast.dismiss).toHaveBeenCalledWith(1)
      expect(toast.success).toHaveBeenCalledWith("Done!")
      expect(result).toEqual({ id: 1 })
    })

    it("shows loading, then error toast on failed operation", async () => {
      const consoleSpy = jest.spyOn(console, "error").mockImplementation()
      const operation = jest.fn().mockRejectedValue(new Error("API Error"))
      const result = await executeWithToast(operation, "Done!", "Operation failed")

      expect(toast.loading).toHaveBeenCalledWith("Loading...")
      expect(toast.dismiss).toHaveBeenCalledWith(1)
      expect(toast.error).toHaveBeenCalledWith("Operation failed")
      expect(result).toBeNull()
      consoleSpy.mockRestore()
    })

    it("uses default error message when errorMessage not provided", async () => {
      const consoleSpy = jest.spyOn(console, "error").mockImplementation()
      const operation = jest.fn().mockRejectedValue(new Error("API Error"))
      await executeWithToast(operation, "Done!")

      expect(toast.error).toHaveBeenCalledWith("Something went wrong")
      consoleSpy.mockRestore()
    })

    it("returns null on failure", async () => {
      const consoleSpy = jest.spyOn(console, "error").mockImplementation()
      const operation = jest.fn().mockRejectedValue(new Error("fail"))
      const result = await executeWithToast(operation, "Done!")
      expect(result).toBeNull()
      consoleSpy.mockRestore()
    })
  })

  describe("extractErrorMessage", () => {
    it("returns 400 message for response-like object with status 400", () => {
      expect(
        extractErrorMessage({ status: 400, statusText: "Bad Request" })
      ).toBe("Invalid request. Please check your input.")
    })

    it("returns 401 message for response-like object with status 401", () => {
      expect(
        extractErrorMessage({ status: 401, statusText: "Unauthorized" })
      ).toBe("You are not authorized. Please log in.")
    })

    it("returns 403 message for response-like object with status 403", () => {
      expect(
        extractErrorMessage({ status: 403, statusText: "Forbidden" })
      ).toBe("You don't have permission for this action.")
    })

    it("returns 404 message for response-like object with status 404", () => {
      expect(
        extractErrorMessage({ status: 404, statusText: "Not Found" })
      ).toBe("Resource not found.")
    })

    it("returns 409 message for response-like object with status 409", () => {
      expect(
        extractErrorMessage({ status: 409, statusText: "Conflict" })
      ).toBe("This resource already exists.")
    })

    it("returns 500 message for response-like object with status 500", () => {
      expect(
        extractErrorMessage({ status: 500, statusText: "Internal Server Error" })
      ).toBe("Server error. Please try again later.")
    })

    it("returns statusText for unrecognized status codes", () => {
      expect(
        extractErrorMessage({ status: 418, statusText: "I'm a teapot" })
      ).toBe("Error: I'm a teapot")
    })

    it("returns network error message for TypeError with fetch", () => {
      const error = new TypeError("Failed to fetch")
      expect(extractErrorMessage(error)).toBe(
        "Network connection failed. Please check your internet."
      )
    })

    it("returns error message for generic Error instances", () => {
      const error = new Error("Something specific went wrong")
      expect(extractErrorMessage(error)).toBe("Something specific went wrong")
    })

    it("returns generic fallback for unknown error types", () => {
      expect(extractErrorMessage("string error")).toBe(
        "An unexpected error occurred"
      )
      expect(extractErrorMessage(null)).toBe("An unexpected error occurred")
      expect(extractErrorMessage(42)).toBe("An unexpected error occurred")
    })
  })
})
