import { render, screen } from '@testing-library/react'
import { ToastProvider } from '@/components/providers/toast-provider'

// Mock sonner Toaster
jest.mock('sonner', () => ({
  Toaster: ({ position, richColors, theme, expand, visibleToasts, closeButton }: any) => (
    <div
      data-testid="toaster"
      data-position={position}
      data-rich-colors={String(richColors)}
      data-theme={theme}
      data-expand={String(expand)}
      data-visible-toasts={visibleToasts}
      data-close-button={String(closeButton)}
    />
  ),
}))

describe('ToastProvider', () => {
  it('renders the Toaster with correct default props', () => {
    render(<ToastProvider />)

    const toaster = screen.getByTestId('toaster')
    expect(toaster).toBeInTheDocument()
    expect(toaster).toHaveAttribute('data-position', 'top-right')
    expect(toaster).toHaveAttribute('data-rich-colors', 'true')
    expect(toaster).toHaveAttribute('data-theme', 'light')
    expect(toaster).toHaveAttribute('data-expand', 'true')
    expect(toaster).toHaveAttribute('data-visible-toasts', '3')
    expect(toaster).toHaveAttribute('data-close-button', 'true')
  })
})
