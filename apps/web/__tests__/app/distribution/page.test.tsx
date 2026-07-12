import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DistributionPage from '@/app/(auth)/distribution/page'
import { withOverride } from '../../../test-utils/fetch-router'
import type { DistributionTarget } from '@/lib/types/distribution'

jest.mock('next-auth/react', () => ({
  useSession: () => ({ status: 'authenticated' }),
}))

jest.mock('@/lib/toast', () => ({
  showSuccessToast: jest.fn(),
  showErrorToast: jest.fn(),
}))

const { showSuccessToast, showErrorToast } = jest.requireMock('@/lib/toast')

const spotifyTarget: DistributionTarget = {
  id: 'dt-spotify',
  user_id: 'u1',
  tenant_id: 't1',
  project_id: null,
  target_type: 'spotify',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  platform_name: 'Spotify: My Show',
  token_expires_at: '2026-02-01T00:00:00Z',
  token_valid: true,
}

const appleTarget: DistributionTarget = {
  id: 'dt-apple',
  user_id: 'u1',
  tenant_id: 't1',
  project_id: null,
  target_type: 'apple_podcasts',
  is_active: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  platform_name: 'Apple Podcasts: My Show',
}

const webhookTarget: DistributionTarget = {
  id: 'dt-webhook',
  user_id: 'u1',
  tenant_id: 't1',
  project_id: null,
  target_type: 'webhook',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  platform_name: 'My webhook',
}

type FetchRouterOpts = {
  targets?: DistributionTarget[]
  listOk?: boolean
}

function mockFetchRouter({
  targets = [spotifyTarget, appleTarget, webhookTarget],
  listOk = true,
}: FetchRouterOpts = {}) {
  return jest.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    if (url === '/api/proxy/distribution-targets' && method === 'GET') {
      return listOk
        ? Promise.resolve({
            ok: true,
            json: async () => ({ targets, total: targets.length, page: 1, page_size: 20, total_pages: 1 }),
          })
        : Promise.resolve({ ok: false })
    }
    return Promise.resolve({ ok: true, json: async () => ({}) })
  }) as jest.Mock
}

describe('DistributionPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    window.history.pushState({}, '', '/distribution')
  })

  it('loads and renders distribution targets', async () => {
    global.fetch = mockFetchRouter()
    render(<DistributionPage />)

    expect(await screen.findByText('Spotify: My Show')).toBeInTheDocument()
    expect(screen.getByText('Apple Podcasts')).toBeInTheDocument()
    expect(screen.getByText('My webhook')).toBeInTheDocument()
    expect(global.fetch).toHaveBeenCalledWith('/api/proxy/distribution-targets')
  })

  it('shows the RSS-model explainer callout', async () => {
    global.fetch = mockFetchRouter()
    render(<DistributionPage />)
    await screen.findByText('Spotify: My Show')

    expect(screen.getByText('How distribution works')).toBeInTheDocument()
    expect(screen.getByText(/public RSS/)).toBeInTheDocument()
  })

  it('shows badges for active/inactive and spotify token validity', async () => {
    global.fetch = mockFetchRouter()
    render(<DistributionPage />)
    const spotifyCard = (await screen.findByText('Spotify: My Show')).closest('div.rounded-lg') as HTMLElement

    expect(within(spotifyCard!).getByText('Active')).toBeInTheDocument()
    expect(within(spotifyCard!).getByText('Token valid')).toBeInTheDocument()
    expect(screen.getByText(/Token expires:/)).toBeInTheDocument()
  })

  it('shows an empty state when there are no targets', async () => {
    global.fetch = mockFetchRouter({ targets: [] })
    render(<DistributionPage />)

    expect(await screen.findByText('No platforms connected')).toBeInTheDocument()
  })

  it('opens the Spotify dialog from the empty-state action', async () => {
    global.fetch = mockFetchRouter({ targets: [] })
    render(<DistributionPage />)
    await screen.findByText('No platforms connected')

    const connectButtons = screen.getAllByRole('button', { name: 'Connect Spotify' })
    await userEvent.click(connectButtons[connectButtons.length - 1])

    expect(screen.getByRole('heading', { name: /connect spotify/i })).toBeInTheDocument()
  })

  it('shows an error toast when the list fails to load', async () => {
    global.fetch = mockFetchRouter({ listOk: false })
    render(<DistributionPage />)

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to load distribution targets')
    )
  })

  it('shows a network error toast when the list fetch rejects', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('boom')) as jest.Mock
    render(<DistributionPage />)

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to load distribution targets: Network error')
    )
  })

  it('opens each connect dialog from the header buttons', async () => {
    global.fetch = mockFetchRouter()
    render(<DistributionPage />)
    await screen.findByText('Spotify: My Show')

    await userEvent.click(screen.getByRole('button', { name: /connect spotify/i }))
    expect(screen.getByRole('heading', { name: /connect spotify/i })).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')

    await userEvent.click(screen.getByRole('button', { name: /connect apple podcasts/i }))
    expect(screen.getByRole('heading', { name: /connect apple podcasts/i })).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')

    await userEvent.click(screen.getByRole('button', { name: /connect webhook/i }))
    expect(screen.getByRole('heading', { name: /connect webhook/i })).toBeInTheDocument()
  })

  it('refetches and shows a success toast when the Apple dialog connects', async () => {
    const fetchMock = withOverride(
      withOverride(
        mockFetchRouter(),
        (url, init) => url === '/api/proxy/distribution-targets/apple/authorize' && (init?.method ?? 'GET') === 'POST',
        () =>
          Promise.resolve({
            ok: true,
            json: async () => ({
              // Mirrors the real contract: message is prose, setup_instructions is a URL
              message: 'Do the thing',
              podcasts_connect_url: 'https://podcastsconnect.apple.com/',
              setup_instructions: 'https://help.apple.com/itc/podcasts_connect/',
            }),
          })
      ),
      (url, init) => url === '/api/proxy/distribution-targets/apple' && (init?.method ?? 'GET') === 'POST',
      () => Promise.resolve({ ok: true, json: async () => ({ id: 'dt-new' }) })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Spotify: My Show')

    await userEvent.click(screen.getByRole('button', { name: /connect apple podcasts/i }))
    await screen.findByText('Do the thing')
    await userEvent.type(screen.getByLabelText(/show id/i), '123')
    await userEvent.type(screen.getByLabelText(/api key/i), 'key')
    await userEvent.click(screen.getByRole('button', { name: /^connect$/i }))

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('Apple Podcasts connected'))
  })

  it('refetches and shows a success toast when the Webhook dialog connects', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/webhook' && (init?.method ?? 'GET') === 'POST',
      () => Promise.resolve({ ok: true, json: async () => ({ id: 'dt-new' }) })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Spotify: My Show')

    await userEvent.click(screen.getByRole('button', { name: /connect webhook/i }))
    await userEvent.type(screen.getByLabelText(/name/i), 'Hook')
    await userEvent.type(screen.getByLabelText(/url/i), 'https://example.com/hook')
    await userEvent.click(screen.getByRole('button', { name: /^connect$/i }))

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('Webhook connected'))
  })

  it('tests a connection and shows a success toast', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/dt-spotify/test' && (init?.method ?? 'GET') === 'POST',
      () =>
        Promise.resolve({
          ok: true,
          json: async () => ({ success: true, platform: 'spotify', message: 'Connection OK' }),
        })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Spotify: My Show')
    await userEvent.click(screen.getByRole('button', { name: /test spotify: my show connection/i }))

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('Connection OK'))
  })

  it('tests a connection and shows an error toast when the platform reports failure', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/dt-spotify/test' && (init?.method ?? 'GET') === 'POST',
      () =>
        Promise.resolve({
          ok: true,
          json: async () => ({ success: false, platform: 'spotify', message: 'Token expired', error: 'expired' }),
        })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Spotify: My Show')
    await userEvent.click(screen.getByRole('button', { name: /test spotify: my show connection/i }))

    await waitFor(() => expect(showErrorToast).toHaveBeenCalledWith('Token expired'))
  })

  it('shows an error toast when the test-connection request fails', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/dt-spotify/test' && (init?.method ?? 'GET') === 'POST',
      () => Promise.resolve({ ok: false, statusText: 'Bad Gateway' })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Spotify: My Show')
    await userEvent.click(screen.getByRole('button', { name: /test spotify: my show connection/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to test connection: Bad Gateway')
    )
  })

  it('shows a network error toast when the test-connection request rejects', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/dt-spotify/test' && (init?.method ?? 'GET') === 'POST',
      () => Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Spotify: My Show')
    await userEvent.click(screen.getByRole('button', { name: /test spotify: my show connection/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to test connection: Network error')
    )
  })

  it('toggles a target active/inactive', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/dt-apple' && (init?.method ?? 'GET') === 'PUT',
      () => Promise.resolve({ ok: true, json: async () => ({ ...appleTarget, is_active: true }) })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Apple Podcasts')
    await userEvent.click(screen.getByRole('button', { name: /activate apple podcasts/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/proxy/distribution-targets/dt-apple',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ is_active: true }),
        })
      )
    })
    expect(showSuccessToast).toHaveBeenCalledWith('Target activated')
  })

  it('shows an error toast when toggling active fails', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/dt-apple' && (init?.method ?? 'GET') === 'PUT',
      () => Promise.resolve({ ok: false, statusText: 'Bad Request' })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Apple Podcasts')
    await userEvent.click(screen.getByRole('button', { name: /activate apple podcasts/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to update target: Bad Request')
    )
  })

  it('shows a network error toast when toggling active rejects', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/dt-apple' && (init?.method ?? 'GET') === 'PUT',
      () => Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Apple Podcasts')
    await userEvent.click(screen.getByRole('button', { name: /activate apple podcasts/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to update target: Network error')
    )
  })

  it('shows the refresh-token action only for spotify targets', async () => {
    global.fetch = mockFetchRouter()
    render(<DistributionPage />)
    await screen.findByText('Spotify: My Show')

    expect(screen.getByRole('button', { name: /refresh spotify: my show token/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /refresh apple podcasts token/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /refresh my webhook token/i })).not.toBeInTheDocument()
  })

  it('refreshes a spotify token', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/dt-spotify/refresh-token' && (init?.method ?? 'GET') === 'POST',
      () => Promise.resolve({ ok: true, json: async () => ({ ...spotifyTarget, token_valid: true }) })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Spotify: My Show')
    await userEvent.click(screen.getByRole('button', { name: /refresh spotify: my show token/i }))

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('Token refreshed'))
  })

  it('shows an error toast when refreshing a token fails', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/dt-spotify/refresh-token' && (init?.method ?? 'GET') === 'POST',
      () => Promise.resolve({ ok: false, statusText: 'Bad Request' })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Spotify: My Show')
    await userEvent.click(screen.getByRole('button', { name: /refresh spotify: my show token/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to refresh token: Bad Request')
    )
  })

  it('shows a network error toast when refreshing a token rejects', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/dt-spotify/refresh-token' && (init?.method ?? 'GET') === 'POST',
      () => Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Spotify: My Show')
    await userEvent.click(screen.getByRole('button', { name: /refresh spotify: my show token/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to refresh token: Network error')
    )
  })

  it('deletes a target', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/dt-webhook' && (init?.method ?? 'GET') === 'DELETE',
      () => Promise.resolve({ ok: true, json: async () => ({}) })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('My webhook')
    await userEvent.click(screen.getByRole('button', { name: /delete my webhook/i }))
    await userEvent.click(screen.getByRole('button', { name: /^delete$/i }))

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('Distribution target deleted'))
    expect(screen.queryByText('My webhook')).not.toBeInTheDocument()
  })

  it('shows an error toast when deletion fails', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/dt-webhook' && (init?.method ?? 'GET') === 'DELETE',
      () => Promise.resolve({ ok: false, statusText: 'Bad Request' })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('My webhook')
    await userEvent.click(screen.getByRole('button', { name: /delete my webhook/i }))
    await userEvent.click(screen.getByRole('button', { name: /^delete$/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to delete target: Bad Request')
    )
  })

  it('shows a network error toast when deletion rejects', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/dt-webhook' && (init?.method ?? 'GET') === 'DELETE',
      () => Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('My webhook')
    await userEvent.click(screen.getByRole('button', { name: /delete my webhook/i }))
    await userEvent.click(screen.getByRole('button', { name: /^delete$/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to delete target: Network error')
    )
  })

  it('closes the delete dialog without deleting when cancelled', async () => {
    global.fetch = mockFetchRouter()
    render(<DistributionPage />)
    await screen.findByText('My webhook')

    await userEvent.click(screen.getByRole('button', { name: /delete my webhook/i }))
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))

    await waitFor(() =>
      expect(screen.queryByText('Delete distribution target?')).not.toBeInTheDocument()
    )
    expect(screen.getByText('My webhook')).toBeInTheDocument()
  })

  it('shows a success toast and strips query params on a successful Spotify OAuth return', async () => {
    window.history.pushState({}, '', '/distribution?success=Spotify+connected')
    global.fetch = mockFetchRouter()
    render(<DistributionPage />)

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('Spotify connected'))
    await waitFor(() => expect(window.location.search).toBe(''))
  })

  it('shows an error toast and strips query params on a failed Spotify OAuth return', async () => {
    window.history.pushState({}, '', '/distribution?error=access_denied')
    global.fetch = mockFetchRouter()
    render(<DistributionPage />)

    await waitFor(() => expect(showErrorToast).toHaveBeenCalledWith('access_denied'))
    await waitFor(() => expect(window.location.search).toBe(''))
  })
})
