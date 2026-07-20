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

let mockResolvedTheme: 'light' | 'dark' = 'light'
jest.mock('@/components/providers/theme-provider', () => ({
  useTheme: () => ({ resolvedTheme: mockResolvedTheme }),
}))

describe('ToastProvider', () => {
  it('renders the Toaster with correct default props', () => {
    mockResolvedTheme = 'light'
    render(<ToastProvider />)

    const toaster = screen.getByTestId('toaster')
    expect(toaster).toBeInTheDocument()
    expect(toaster).toHaveAttribute('data-position', 'top-right')
    expect(toaster).toHaveAttribute('data-rich-colors', 'true')
    expect(toaster).toHaveAttribute('data-expand', 'true')
    expect(toaster).toHaveAttribute('data-visible-toasts', '3')
    expect(toaster).toHaveAttribute('data-close-button', 'true')
  })

  it('binds the toaster theme to the resolved theme (dark mode is not stuck on light)', () => {
    mockResolvedTheme = 'dark'
    render(<ToastProvider />)

    expect(screen.getByTestId('toaster')).toHaveAttribute('data-theme', 'dark')
  })

  it('uses light theme when the resolved theme is light', () => {
    mockResolvedTheme = 'light'
    render(<ToastProvider />)

    expect(screen.getByTestId('toaster')).toHaveAttribute('data-theme', 'light')
  })
})
