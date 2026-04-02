import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { ThemeProvider, useTheme } from '@/components/providers/theme-provider'

function ThemeConsumer() {
  const { theme, setTheme, resolvedTheme } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolvedTheme}</span>
      <button onClick={() => setTheme('dark')}>Set Dark</button>
      <button onClick={() => setTheme('light')}>Set Light</button>
      <button onClick={() => setTheme('system')}>Set System</button>
    </div>
  )
}

describe('ThemeProvider', () => {
  let localStorageMock: Record<string, string>

  beforeEach(() => {
    localStorageMock = {}
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: (key: string) => localStorageMock[key] ?? null,
        setItem: (key: string, value: string) => { localStorageMock[key] = value },
        removeItem: (key: string) => { delete localStorageMock[key] },
        clear: () => { localStorageMock = {} },
      },
      writable: true,
    })

    Object.defineProperty(window, 'matchMedia', {
      value: jest.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      })),
      writable: true,
    })

    document.documentElement.classList.remove('dark')
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('renders children', () => {
    render(
      <ThemeProvider>
        <span>child</span>
      </ThemeProvider>
    )
    expect(screen.getByText('child')).toBeInTheDocument()
  })

  it('provides theme context to children', () => {
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    expect(screen.getByTestId('theme')).toBeInTheDocument()
  })

  it('defaults to system theme', async () => {
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    await act(async () => {})
    expect(screen.getByTestId('theme').textContent).toBe('system')
  })

  it('loads saved theme from localStorage', async () => {
    localStorageMock['theme'] = 'dark'
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    await act(async () => {})
    expect(screen.getByTestId('theme').textContent).toBe('dark')
  })

  it('ignores invalid localStorage theme values', async () => {
    localStorageMock['theme'] = 'invalid-theme'
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    await act(async () => {})
    expect(screen.getByTestId('theme').textContent).toBe('system')
  })

  it('applies dark class to document when dark theme is set', async () => {
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    await act(async () => {})

    await userEvent.click(screen.getByText('Set Dark'))
    await act(async () => {})

    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('removes dark class from document when light theme is set', async () => {
    document.documentElement.classList.add('dark')
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    await act(async () => {})

    await userEvent.click(screen.getByText('Set Light'))
    await act(async () => {})

    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('persists theme choice to localStorage', async () => {
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    await act(async () => {})

    await userEvent.click(screen.getByText('Set Dark'))
    await act(async () => {})

    expect(localStorageMock['theme']).toBe('dark')
  })

  it('resolves system theme to light when system preference is light', async () => {
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    await act(async () => {})

    await userEvent.click(screen.getByText('Set System'))
    await act(async () => {})

    expect(screen.getByTestId('resolved').textContent).toBe('light')
  })

  it('resolves system theme to dark when system preference is dark', async () => {
    Object.defineProperty(window, 'matchMedia', {
      value: jest.fn().mockImplementation((query: string) => ({
        matches: true,
        media: query,
        onchange: null,
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      })),
      writable: true,
    })

    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )
    await act(async () => {})

    await userEvent.click(screen.getByText('Set System'))
    await act(async () => {})

    expect(screen.getByTestId('resolved').textContent).toBe('dark')
  })

  it('throws if useTheme is used outside ThemeProvider', () => {
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<ThemeConsumer />)).toThrow(
      'useTheme must be used within ThemeProvider'
    )
    consoleError.mockRestore()
  })
})
