import { render, screen } from '@testing-library/react'
import Home from '@/app/page'

const mockPush = jest.fn()
let mockSessionValue: { data: unknown; status: string }

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}))

jest.mock('next-auth/react', () => ({
  useSession: () => mockSessionValue,
}))

describe('Home', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders a loading message and does not redirect while the session is loading', () => {
    mockSessionValue = { data: null, status: 'loading' }
    render(<Home />)

    expect(screen.getByText('Loading...')).toBeInTheDocument()
    expect(mockPush).not.toHaveBeenCalled()
  })

  it('redirects to /dashboard when a session exists', () => {
    mockSessionValue = { data: { user: { id: '1' } }, status: 'authenticated' }
    render(<Home />)

    expect(mockPush).toHaveBeenCalledWith('/dashboard')
  })

  it('redirects to /login when there is no session', () => {
    mockSessionValue = { data: null, status: 'unauthenticated' }
    render(<Home />)

    expect(mockPush).toHaveBeenCalledWith('/login')
  })
})
