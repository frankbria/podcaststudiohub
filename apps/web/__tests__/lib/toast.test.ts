import { showSuccessToast, showErrorToast, showLoadingToast, dismissToast, executeWithToast } from '@/lib/toast'

// Mock sonner
jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    loading: jest.fn().mockReturnValue('toast-id-1'),
    dismiss: jest.fn(),
  },
}))

import { toast } from 'sonner'

describe('toast utilities', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('showSuccessToast', () => {
    it('calls toast.success with the message', () => {
      showSuccessToast('Operation succeeded')
      expect(toast.success).toHaveBeenCalledWith('Operation succeeded')
    })
  })

  describe('showErrorToast', () => {
    it('calls toast.error with the message', () => {
      showErrorToast('Operation failed')
      expect(toast.error).toHaveBeenCalledWith('Operation failed')
    })
  })

  describe('showLoadingToast', () => {
    it('calls toast.loading and returns the toast id', () => {
      const id = showLoadingToast('Loading...')
      expect(toast.loading).toHaveBeenCalledWith('Loading...')
      expect(id).toBe('toast-id-1')
    })
  })

  describe('dismissToast', () => {
    it('calls toast.dismiss with the given id', () => {
      dismissToast('toast-id-1')
      expect(toast.dismiss).toHaveBeenCalledWith('toast-id-1')
    })

    it('calls toast.dismiss with a numeric id', () => {
      dismissToast(42)
      expect(toast.dismiss).toHaveBeenCalledWith(42)
    })
  })

  describe('executeWithToast', () => {
    it('shows success toast and returns result on success', async () => {
      const operation = jest.fn().mockResolvedValue({ data: 'result' })
      const result = await executeWithToast(operation, 'Success!', 'Error!')

      expect(result).toEqual({ data: 'result' })
      expect(toast.loading).toHaveBeenCalledWith('Loading...')
      expect(toast.dismiss).toHaveBeenCalledWith('toast-id-1')
      expect(toast.success).toHaveBeenCalledWith('Success!')
      expect(toast.error).not.toHaveBeenCalled()
    })

    it('shows error toast and returns null on failure', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {})
      const operation = jest.fn().mockRejectedValue(new Error('Network error'))
      const result = await executeWithToast(operation, 'Success!', 'Custom error message')

      expect(result).toBeNull()
      expect(toast.loading).toHaveBeenCalledWith('Loading...')
      expect(toast.dismiss).toHaveBeenCalledWith('toast-id-1')
      expect(toast.error).toHaveBeenCalledWith('Custom error message')
      expect(toast.success).not.toHaveBeenCalled()
      consoleSpy.mockRestore()
    })

    it('uses default error message when errorMessage not provided', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {})
      const operation = jest.fn().mockRejectedValue(new Error('oops'))
      await executeWithToast(operation, 'Success!')

      expect(toast.error).toHaveBeenCalledWith('Something went wrong')
      consoleSpy.mockRestore()
    })
  })
})
