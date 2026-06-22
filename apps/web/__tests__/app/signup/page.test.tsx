import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SignupPage from '@/app/signup/page'

const mockPush = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}))

async function fillAndSubmit() {
  await userEvent.type(screen.getByLabelText(/email/i), 'a@b.com')
  await userEvent.type(screen.getByLabelText(/password/i), 'password123')
  await userEvent.click(screen.getByRole('button', { name: /sign up/i }))
}

describe('SignupPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('resets loading before redirecting on success', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({}) }) as jest.Mock

    render(<SignupPage />)
    await fillAndSubmit()

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/login?registered=true'))
    // Button text reset (no longer "Creating account...") — proves loading=false before redirect.
    expect(screen.getByRole('button', { name: /sign up/i })).toBeInTheDocument()
  })

  it('trims whitespace from the full name before sending', async () => {
    const fetchMock = jest
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({}) }) as jest.Mock
    global.fetch = fetchMock

    render(<SignupPage />)
    await userEvent.type(screen.getByLabelText(/full name/i), '  Jane Doe  ')
    await fillAndSubmit()

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.full_name).toBe('Jane Doe')
  })

  it('shows the error and resets loading on failure', async () => {
    global.fetch = jest
      .fn()
      .mockResolvedValue({ ok: false, json: async () => ({ detail: 'Email taken' }) }) as jest.Mock

    render(<SignupPage />)
    await fillAndSubmit()

    expect(await screen.findByText('Email taken')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign up/i })).toBeEnabled()
    expect(mockPush).not.toHaveBeenCalled()
  })
})
