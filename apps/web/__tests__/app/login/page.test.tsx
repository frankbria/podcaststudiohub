import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LoginPage from '@/app/login/page'

const mockPush = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}))

const mockSignIn = jest.fn()

jest.mock('next-auth/react', () => ({
  signIn: (...args: unknown[]) => mockSignIn(...args),
}))

async function fillAndSubmit() {
  await userEvent.type(screen.getByLabelText(/email/i), 'a@b.com')
  await userEvent.type(screen.getByLabelText(/password/i), 'password123')
  await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
}

describe('LoginPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    window.history.replaceState({}, '', '/login')
  })

  it('shows the registered confirmation and clears the query param', () => {
    window.history.replaceState({}, '', '/login?registered=true')

    render(<LoginPage />)

    expect(screen.getByRole('status')).toHaveTextContent(/account created/i)
    // param cleared so a refresh doesn't re-show the banner
    expect(window.location.search).toBe('')
  })

  it('does not show the confirmation without ?registered=true', () => {
    render(<LoginPage />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('redirects to /dashboard on successful sign-in', async () => {
    mockSignIn.mockResolvedValue({ error: null })

    render(<LoginPage />)
    await fillAndSubmit()

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/dashboard'))
    expect(mockSignIn).toHaveBeenCalledWith('credentials', {
      email: 'a@b.com',
      password: 'password123',
      redirect: false,
    })
  })

  it('shows an error and resets loading when credentials are invalid', async () => {
    mockSignIn.mockResolvedValue({ error: 'CredentialsSignin' })

    render(<LoginPage />)
    await fillAndSubmit()

    expect(await screen.findByText('Invalid email or password')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeEnabled()
    expect(mockPush).not.toHaveBeenCalled()
  })

  it('announces the error via role=alert and marks the inputs invalid', async () => {
    mockSignIn.mockResolvedValue({ error: 'CredentialsSignin' })

    render(<LoginPage />)
    await fillAndSubmit()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Invalid email or password')

    const email = screen.getByLabelText(/email/i)
    expect(email).toHaveAttribute('aria-invalid', 'true')
    expect(email).toHaveAttribute('aria-describedby', 'login-error')
    expect(alert).toHaveAttribute('id', 'login-error')
  })

  it('shows a generic error when signIn throws', async () => {
    mockSignIn.mockRejectedValue(new Error('network down'))

    render(<LoginPage />)
    await fillAndSubmit()

    expect(await screen.findByText('An error occurred. Please try again.')).toBeInTheDocument()
    expect(mockPush).not.toHaveBeenCalled()
  })

  it('shows the loading label while the request is in flight', async () => {
    let resolveSignIn: (value: { error: null }) => void = () => {}
    mockSignIn.mockImplementation(
      () => new Promise((resolve) => { resolveSignIn = resolve })
    )

    render(<LoginPage />)
    await userEvent.type(screen.getByLabelText(/email/i), 'a@b.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'password123')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('button', { name: /signing in/i })).toBeInTheDocument()

    resolveSignIn({ error: null })
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/dashboard'))
  })
})
