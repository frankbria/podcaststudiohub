import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { MainNav } from '@/components/navigation/MainNav'

const mockPush = jest.fn()
const mockSignOut = jest.fn().mockResolvedValue({})

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}))

jest.mock('next-auth/react', () => ({
  useSession: jest.fn(),
  signOut: (...args: unknown[]) => mockSignOut(...args),
}))

jest.mock('@/components/providers/theme-provider', () => ({
  useTheme: () => ({
    theme: 'system',
    setTheme: jest.fn(),
    resolvedTheme: 'light',
  }),
}))

const mockUseSession = jest.requireMock('next-auth/react').useSession as jest.Mock

describe('MainNav', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // Reset localStorage / sessionStorage
    Object.defineProperty(window, 'localStorage', {
      value: { clear: jest.fn(), removeItem: jest.fn(), getItem: jest.fn(), setItem: jest.fn() },
      writable: true,
    })
    Object.defineProperty(window, 'sessionStorage', {
      value: { clear: jest.fn(), removeItem: jest.fn(), getItem: jest.fn(), setItem: jest.fn() },
      writable: true,
    })
  })

  it('renders nothing when unauthenticated', () => {
    mockUseSession.mockReturnValue({ data: null, status: 'unauthenticated' })
    const { container } = render(<MainNav />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when loading', () => {
    mockUseSession.mockReturnValue({ data: null, status: 'loading' })
    const { container } = render(<MainNav />)
    expect(container.firstChild).toBeNull()
  })

  it('renders navigation when authenticated', () => {
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    render(<MainNav />)
    expect(screen.getByRole('navigation', { name: /main navigation/i })).toBeInTheDocument()
    expect(screen.getByText('Podcastfy Studio')).toBeInTheDocument()
  })

  it('renders user menu button with aria-label', () => {
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    render(<MainNav />)
    expect(screen.getByRole('button', { name: /user menu/i })).toBeInTheDocument()
  })

  it('shows user name and email in dropdown when menu is opened', async () => {
    const user = userEvent.setup()
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    render(<MainNav />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))

    expect(screen.getByText('Jane Doe')).toBeInTheDocument()
    expect(screen.getByText('jane@example.com')).toBeInTheDocument()
  })

  it('shows logout option in dropdown', async () => {
    const user = userEvent.setup()
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    render(<MainNav />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))

    expect(screen.getByRole('menuitem', { name: /logout/i })).toBeInTheDocument()
  })

  it('calls signOut and redirects to login on logout click', async () => {
    const user = userEvent.setup()
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    render(<MainNav />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))
    await user.click(screen.getByRole('menuitem', { name: /logout/i }))

    await waitFor(() => {
      expect(mockSignOut).toHaveBeenCalledWith({ redirect: false })
    })
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/login')
    })
  })

  it('clears localStorage and sessionStorage on logout', async () => {
    const user = userEvent.setup()
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    const clearLocalStorage = jest.spyOn(window.localStorage, 'clear')
    const clearSessionStorage = jest.spyOn(window.sessionStorage, 'clear')

    render(<MainNav />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))
    await user.click(screen.getByRole('menuitem', { name: /logout/i }))

    await waitFor(() => {
      expect(clearLocalStorage).toHaveBeenCalled()
      expect(clearSessionStorage).toHaveBeenCalled()
    })
  })

  it('falls back to "User" when session name is missing', async () => {
    const user = userEvent.setup()
    mockUseSession.mockReturnValue({
      data: { user: { name: null, email: 'jane@example.com' } },
      status: 'authenticated',
    })
    render(<MainNav />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))

    expect(screen.getByText('User')).toBeInTheDocument()
  })

  it('dashboard link points to /dashboard', () => {
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    render(<MainNav />)
    const link = screen.getByRole('link', { name: /podcastfy studio/i })
    expect(link).toHaveAttribute('href', '/dashboard')
  })

  it('renders a Dashboard nav link pointing to /dashboard', () => {
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    render(<MainNav />)
    const link = screen.getByRole('link', { name: /^dashboard$/i })
    expect(link).toHaveAttribute('href', '/dashboard')
  })

  it('renders a Distribution nav link pointing to /distribution', () => {
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    render(<MainNav />)
    const link = screen.getByRole('link', { name: /^distribution$/i })
    expect(link).toHaveAttribute('href', '/distribution')
  })
})
