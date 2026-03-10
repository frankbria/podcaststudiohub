import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { MainNav } from '@/components/navigation/MainNav'

const mockPush = jest.fn()
const mockSignOut = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}))

jest.mock('next-auth/react', () => ({
  useSession: jest.fn(),
  signOut: (...args: unknown[]) => mockSignOut(...args),
}))

import { useSession } from 'next-auth/react'

const mockUseSession = useSession as jest.Mock

describe('MainNav', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders nothing when unauthenticated', () => {
    mockUseSession.mockReturnValue({ data: null, status: 'unauthenticated' })
    const { container } = render(<MainNav />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing while loading', () => {
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
    expect(screen.getByRole('navigation')).toBeInTheDocument()
  })

  it('shows app logo linking to /dashboard', () => {
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    render(<MainNav />)
    const logo = screen.getByRole('link', { name: /podcastfy/i })
    expect(logo).toHaveAttribute('href', '/dashboard')
  })

  it('renders user menu button with aria-label', () => {
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    render(<MainNav />)
    expect(screen.getByRole('button', { name: /user menu/i })).toBeInTheDocument()
  })

  it('opens dropdown and shows user info on button click', async () => {
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    const user = userEvent.setup()
    render(<MainNav />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))

    expect(screen.getByText('Jane Doe')).toBeInTheDocument()
    expect(screen.getByText('jane@example.com')).toBeInTheDocument()
  })

  it('shows logout option in dropdown', async () => {
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    const user = userEvent.setup()
    render(<MainNav />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))

    expect(screen.getByRole('menuitem', { name: /logout/i })).toBeInTheDocument()
  })

  it('calls signOut and redirects to /login on logout click', async () => {
    mockSignOut.mockResolvedValue(undefined)
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    const user = userEvent.setup()
    render(<MainNav />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))
    await user.click(screen.getByRole('menuitem', { name: /logout/i }))

    await waitFor(() => {
      expect(mockSignOut).toHaveBeenCalledWith({ redirect: false })
      expect(mockPush).toHaveBeenCalledWith('/login')
    })
  })

  it('disables logout button while logging out', async () => {
    // signOut never resolves during this test to simulate in-progress state
    mockSignOut.mockReturnValue(new Promise(() => {}))
    mockUseSession.mockReturnValue({
      data: { user: { name: 'Jane Doe', email: 'jane@example.com' } },
      status: 'authenticated',
    })
    const user = userEvent.setup()
    render(<MainNav />)

    // Open menu and click logout (menu closes on click per dropdown behavior)
    await user.click(screen.getByRole('button', { name: /user menu/i }))
    await user.click(screen.getByRole('menuitem', { name: /logout/i }))

    // Re-open the menu to inspect the disabled state
    await user.click(screen.getByRole('button', { name: /user menu/i }))

    await waitFor(() => {
      const logoutItem = screen.getByRole('menuitem', { name: /logout/i })
      expect(logoutItem).toHaveAttribute('aria-disabled', 'true')
    })
  })

  it('shows fallback "User" name when session has no name', async () => {
    mockUseSession.mockReturnValue({
      data: { user: { name: null, email: 'anon@example.com' } },
      status: 'authenticated',
    })
    const user = userEvent.setup()
    render(<MainNav />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))

    expect(screen.getByText('User')).toBeInTheDocument()
  })
})
