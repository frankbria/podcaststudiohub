import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { ThemeToggle } from '@/components/ThemeToggle'
import { ThemeProvider } from '@/components/providers/theme-provider'

// Mock matchMedia
const mockMatchMedia = (matches: boolean) =>
  jest.fn().mockImplementation((query) => ({
    matches,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  }))

function renderWithTheme(ui: React.ReactElement, prefersDark = false) {
  window.matchMedia = mockMatchMedia(prefersDark)
  return render(<ThemeProvider>{ui}</ThemeProvider>)
}

describe('ThemeToggle', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: jest.fn(() => null),
        setItem: jest.fn(),
        removeItem: jest.fn(),
        clear: jest.fn(),
      },
      writable: true,
    })
  })

  afterEach(() => {
    document.documentElement.classList.remove('dark')
    jest.clearAllMocks()
  })

  it('renders the toggle button', () => {
    renderWithTheme(<ThemeToggle />)
    expect(screen.getByRole('button', { name: /toggle theme/i })).toBeInTheDocument()
  })

  it('shows sun icon in light mode', () => {
    renderWithTheme(<ThemeToggle />, false)
    const button = screen.getByRole('button', { name: /toggle theme/i })
    expect(button).toBeInTheDocument()
    // Sun icon should be present (via aria-label or title)
    expect(button.querySelector('svg')).toBeInTheDocument()
  })

  it('cycles through themes on click', async () => {
    const user = userEvent.setup()
    renderWithTheme(<ThemeToggle />)
    const button = screen.getByRole('button', { name: /toggle theme/i })

    // Initial: system -> click -> light
    await act(async () => {
      await user.click(button)
    })
    expect(window.localStorage.setItem).toHaveBeenCalledWith('theme', 'light')

    // light -> click -> dark
    await act(async () => {
      await user.click(button)
    })
    expect(window.localStorage.setItem).toHaveBeenCalledWith('theme', 'dark')

    // dark -> click -> system
    await act(async () => {
      await user.click(button)
    })
    expect(window.localStorage.setItem).toHaveBeenCalledWith('theme', 'system')
  })

  it('is keyboard accessible', () => {
    renderWithTheme(<ThemeToggle />)
    const button = screen.getByRole('button', { name: /toggle theme/i })
    expect(button).not.toHaveAttribute('tabIndex', '-1')
  })

  it('has aria-label for accessibility', () => {
    renderWithTheme(<ThemeToggle />)
    const button = screen.getByRole('button', { name: /toggle theme/i })
    expect(button).toHaveAttribute('aria-label')
  })
})
