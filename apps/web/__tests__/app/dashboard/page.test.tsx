import { render, screen, waitFor } from '@testing-library/react'
import DashboardPage from '@/app/(auth)/dashboard/page'

const mockPush = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}))

jest.mock('next-auth/react', () => ({
  useSession: () => ({ status: 'authenticated' }),
}))

jest.mock('@/lib/toast', () => ({
  showSuccessToast: jest.fn(),
  showErrorToast: jest.fn(),
}))

const { showErrorToast } = jest.requireMock('@/lib/toast')

describe('DashboardPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders projects on successful load', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          { id: '1', title: 'My First Podcast', description: null, episode_count: 2, created_at: '2026-01-01' },
        ],
      }),
    }) as jest.Mock

    render(<DashboardPage />)

    expect(await screen.findByText('My First Podcast')).toBeInTheDocument()
    expect(global.fetch).toHaveBeenCalledWith('/api/proxy/projects')
  })

  it('shows an error toast when the load fails', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: false }) as jest.Mock

    render(<DashboardPage />)

    await waitFor(() => {
      expect(showErrorToast).toHaveBeenCalledWith('Failed to load projects')
    })
  })

  it('shows an error toast on a network error', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('boom')) as jest.Mock

    render(<DashboardPage />)

    await waitFor(() => {
      expect(showErrorToast).toHaveBeenCalledWith('Failed to load projects: Network error')
    })
  })
})
