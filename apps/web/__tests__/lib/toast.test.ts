import {
  showSuccessToast,
  showErrorToast,
  showLoadingToast,
  dismissToast,
  extractErrorMessage,
} from '@/lib/toast'

// Mock sonner
jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    loading: jest.fn().mockReturnValue(42),
    dismiss: jest.fn(),
  },
}))

import { toast } from 'sonner'

describe('toast utilities', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('showSuccessToast', () => {
    it('calls toast.success with the provided message', () => {
      showSuccessToast('Project created successfully')
      expect(toast.success).toHaveBeenCalledWith('Project created successfully')
    })
  })

  describe('showErrorToast', () => {
    it('calls toast.error with the provided message', () => {
      showErrorToast('Failed to create project')
      expect(toast.error).toHaveBeenCalledWith('Failed to create project')
    })
  })

  describe('showLoadingToast', () => {
    it('calls toast.loading and returns the toast id', () => {
      const id = showLoadingToast('Creating project...')
      expect(toast.loading).toHaveBeenCalledWith('Creating project...')
      expect(id).toBe(42)
    })
  })

  describe('dismissToast', () => {
    it('calls toast.dismiss with the toast id', () => {
      dismissToast(42)
      expect(toast.dismiss).toHaveBeenCalledWith(42)
    })

    it('accepts string toast ids', () => {
      dismissToast('string-id')
      expect(toast.dismiss).toHaveBeenCalledWith('string-id')
    })
  })

  describe('extractErrorMessage', () => {
    it('returns message for 400 status', () => {
      expect(extractErrorMessage({ status: 400, statusText: 'Bad Request' })).toBe('Invalid request. Please check your input.')
    })

    it('returns message for 401 status', () => {
      expect(extractErrorMessage({ status: 401, statusText: 'Unauthorized' })).toBe('You are not authorized. Please log in.')
    })

    it('returns message for 403 status', () => {
      expect(extractErrorMessage({ status: 403, statusText: 'Forbidden' })).toBe("You don't have permission for this action.")
    })

    it('returns message for 404 status', () => {
      expect(extractErrorMessage({ status: 404, statusText: 'Not Found' })).toBe('Resource not found.')
    })

    it('returns message for 409 status', () => {
      expect(extractErrorMessage({ status: 409, statusText: 'Conflict' })).toBe('This resource already exists.')
    })

    it('returns message for 500 status', () => {
      expect(extractErrorMessage({ status: 500, statusText: 'Internal Server Error' })).toBe('Server error. Please try again later.')
    })

    it('returns statusText for unknown status codes', () => {
      expect(extractErrorMessage({ status: 422, statusText: 'Unprocessable Entity' })).toBe('Error: Unprocessable Entity')
    })

    it('returns network error message for fetch TypeError', () => {
      const error = new TypeError('Failed to fetch')
      expect(extractErrorMessage(error)).toBe('Network connection failed. Please check your internet.')
    })

    it('returns error message for generic Error', () => {
      const error = new Error('Something went wrong')
      expect(extractErrorMessage(error)).toBe('Something went wrong')
    })

    it('returns fallback message for unknown error types', () => {
      expect(extractErrorMessage(null)).toBe('An unexpected error occurred')
      expect(extractErrorMessage(undefined)).toBe('An unexpected error occurred')
      expect(extractErrorMessage('string error')).toBe('An unexpected error occurred')
    })
  })
})
