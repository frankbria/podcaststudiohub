import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { ToastProvider } from '@/components/providers/toast-provider'

// Mock sonner's Toaster component
jest.mock('sonner', () => ({
  Toaster: ({ position, richColors, theme, expand, visibleToasts, closeButton }: any) => (
    <div
      data-testid="sonner-toaster"
      data-position={position}
      data-rich-colors={String(richColors)}
      data-theme={theme}
      data-expand={String(expand)}
      data-visible-toasts={visibleToasts}
      data-close-button={String(closeButton)}
    />
  ),
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    loading: jest.fn(),
    dismiss: jest.fn(),
  },
}))

describe('ToastProvider', () => {
  it('renders the Toaster component', () => {
    render(<ToastProvider />)
    expect(screen.getByTestId('sonner-toaster')).toBeInTheDocument()
  })

  it('configures Toaster with top-right position', () => {
    render(<ToastProvider />)
    expect(screen.getByTestId('sonner-toaster')).toHaveAttribute('data-position', 'top-right')
  })

  it('configures Toaster with richColors enabled', () => {
    render(<ToastProvider />)
    expect(screen.getByTestId('sonner-toaster')).toHaveAttribute('data-rich-colors', 'true')
  })

  it('configures Toaster with light theme', () => {
    render(<ToastProvider />)
    expect(screen.getByTestId('sonner-toaster')).toHaveAttribute('data-theme', 'light')
  })

  it('configures Toaster with visibleToasts 3', () => {
    render(<ToastProvider />)
    expect(screen.getByTestId('sonner-toaster')).toHaveAttribute('data-visible-toasts', '3')
  })

  it('configures Toaster with closeButton enabled', () => {
    render(<ToastProvider />)
    expect(screen.getByTestId('sonner-toaster')).toHaveAttribute('data-close-button', 'true')
  })
})
