import { render, screen, act } from '@testing-library/react'
import * as React from 'react'
import { ThemeProvider, useTheme } from '@/components/providers/theme-provider'

// Helper component to expose theme context values
function ThemeConsumer() {
  const { theme, setTheme, resolvedTheme } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved-theme">{resolvedTheme}</span>
      <button onClick={() => setTheme('dark')}>Set Dark</button>
      <button onClick={() => setTheme('light')}>Set Light</button>
      <button onClick={() => setTheme('system')}>Set System</button>
    </div>
  )
}

// Mock matchMedia
const mockMatchMedia = (matches: boolean) => {
  const listeners: Array<(e: MediaQueryListEvent) => void> = []
  return jest.fn().mockImplementation((query) => ({
    matches,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: (type: string, listener: (e: MediaQueryListEvent) => void) => {
      listeners.push(listener)
    },
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
    _listeners: listeners,
  }))
}

describe('ThemeProvider', () => {
  let localStorageMock: { [key: string]: string }

  beforeEach(() => {
    localStorageMock = {}
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: jest.fn((key: string) => localStorageMock[key] || null),
        setItem: jest.fn((key: string, value: string) => {
          localStorageMock[key] = value
        }),
        removeItem: jest.fn((key: string) => {
          delete localStorageMock[key]
        }),
        clear: jest.fn(() => {
          localStorageMock = {}
        }),
      },
      writable: true,
    })
  })

  afterEach(() => {
    document.documentElement.classList.remove('dark')
    jest.clearAllMocks()
  })

  it('renders children', () => {
    window.matchMedia = mockMatchMedia(false)
    render(
      <ThemeProvider>
        <span>child</span>
      </ThemeProvider>
    )
    expect(screen.getByText('child')).toBeInTheDocument()
  })

  it('defaults to system theme when no localStorage value', () => {
    window.matchMedia = mockMatchMedia(false)
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    expect(screen.getByTestId('theme').textContent).toBe('system')
  })

  it('resolves to light when system preference is light', () => {
    window.matchMedia = mockMatchMedia(false)
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    expect(screen.getByTestId('resolved-theme').textContent).toBe('light')
  })

  it('resolves to dark when system preference is dark', () => {
    window.matchMedia = mockMatchMedia(true)
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    expect(screen.getByTestId('resolved-theme').textContent).toBe('dark')
  })

  it('loads saved theme from localStorage', () => {
    window.matchMedia = mockMatchMedia(false)
    localStorageMock['theme'] = 'dark'
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    expect(screen.getByTestId('theme').textContent).toBe('dark')
    expect(screen.getByTestId('resolved-theme').textContent).toBe('dark')
  })

  it('sets dark class on document when dark theme is resolved', () => {
    window.matchMedia = mockMatchMedia(false)
    localStorageMock['theme'] = 'dark'
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('removes dark class on document when light theme is resolved', () => {
    window.matchMedia = mockMatchMedia(false)
    document.documentElement.classList.add('dark')
    localStorageMock['theme'] = 'light'
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('persists theme to localStorage when setTheme is called', () => {
    window.matchMedia = mockMatchMedia(false)
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    act(() => {
      screen.getByText('Set Dark').click()
    })
    expect(window.localStorage.setItem).toHaveBeenCalledWith('theme', 'dark')
  })

  it('updates resolved theme immediately when setTheme is called', () => {
    window.matchMedia = mockMatchMedia(false)
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    act(() => {
      screen.getByText('Set Dark').click()
    })
    expect(screen.getByTestId('resolved-theme').textContent).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('throws error when useTheme is used outside ThemeProvider', () => {
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<ThemeConsumer />)).toThrow(
      'useTheme must be used within ThemeProvider'
    )
    consoleSpy.mockRestore()
  })
})
