import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DistributionPage from '@/app/(auth)/projects/[id]/distribution/page'
import { withOverride } from '../../../../../test-utils/fetch-router'

const mockPush = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({ id: 'p1' }),
}))

jest.mock('next-auth/react', () => ({
  useSession: () => ({ status: 'authenticated' }),
}))

jest.mock('@/lib/toast', () => ({
  showSuccessToast: jest.fn(),
  showErrorToast: jest.fn(),
}))

const { showSuccessToast, showErrorToast } = jest.requireMock('@/lib/toast')

const project = {
  id: 'p1',
  name: 'My Podcast',
  description: 'A show',
  podcast_metadata: {
    show_title: 'My Podcast Show',
    author: 'Jane Doe',
    description: 'A great show about things',
  },
}

const feed = {
  id: 'f1',
  project_id: 'p1',
  tenant_id: 't1',
  s3_key: 'feeds/p1.xml',
  public_url: 'https://cdn.example.com/feeds/p1.xml',
  validation_status: {},
  last_generated: '2026-01-01T12:00:00Z',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T12:00:00Z',
}

type FetchRouterOpts = {
  feedStatus?: 200 | 404 | 500
  projectOk?: boolean
}

function mockFetchRouter({ feedStatus = 200, projectOk = true }: FetchRouterOpts = {}) {
  return jest.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    if (url === '/api/proxy/projects/p1' && method === 'GET') {
      return projectOk
        ? Promise.resolve({ ok: true, json: async () => project })
        : Promise.resolve({ ok: false, status: 500 })
    }
    if (url === '/api/proxy/projects/p1/rss-feed' && method === 'GET') {
      if (feedStatus === 200) {
        return Promise.resolve({ ok: true, status: 200, json: async () => feed })
      }
      return Promise.resolve({ ok: false, status: feedStatus })
    }
    return Promise.resolve({ ok: true, json: async () => ({}) })
  }) as jest.Mock
}

describe('DistributionPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('loads and renders the RSS feed card', async () => {
    global.fetch = mockFetchRouter()
    render(<DistributionPage />)

    expect(await screen.findByText('Podcast RSS Feed')).toBeInTheDocument()
    expect(screen.getByText('https://cdn.example.com/feeds/p1.xml')).toBeInTheDocument()
    expect(screen.getByText(/Last generated:/)).toBeInTheDocument()
    expect(screen.getByText('Not yet validated')).toBeInTheDocument()
  })

  it('shows an empty state with a Generate RSS feed CTA on 404', async () => {
    global.fetch = mockFetchRouter({ feedStatus: 404 })
    render(<DistributionPage />)

    expect(await screen.findByText('No RSS feed yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate RSS feed' })).toBeInTheDocument()
  })

  it('shows an error toast for a non-404 non-2xx feed load failure', async () => {
    global.fetch = mockFetchRouter({ feedStatus: 500 })
    render(<DistributionPage />)

    await waitFor(() => expect(showErrorToast).toHaveBeenCalledWith('Failed to load RSS feed'))
    expect(await screen.findByText('No RSS feed yet')).toBeInTheDocument()
  })

  it('shows a network error toast when the feed fetch rejects', async () => {
    global.fetch = jest.fn((url: string) => {
      if (url === '/api/proxy/projects/p1/rss-feed') {
        return Promise.reject(new Error('boom'))
      }
      return Promise.resolve({ ok: true, json: async () => project })
    }) as jest.Mock
    render(<DistributionPage />)

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to load RSS feed: Network error')
    )
  })

  it('navigates back to the project page', async () => {
    global.fetch = mockFetchRouter()
    render(<DistributionPage />)
    await screen.findByText('Podcast RSS Feed')

    await userEvent.click(screen.getByRole('button', { name: '← Back to Project' }))
    expect(mockPush).toHaveBeenCalledWith('/projects/p1')
  })

  it('copies the feed URL to the clipboard', async () => {
    const writeText = jest.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })

    global.fetch = mockFetchRouter()
    render(<DistributionPage />)
    await screen.findByText('Podcast RSS Feed')

    await userEvent.click(screen.getByRole('button', { name: 'Copy feed URL' }))

    await waitFor(() => expect(writeText).toHaveBeenCalledWith('https://cdn.example.com/feeds/p1.xml'))
    expect(showSuccessToast).toHaveBeenCalledWith('Feed URL copied to clipboard')
  })

  it('shows an error toast when clipboard copy fails', async () => {
    const writeText = jest.fn().mockRejectedValue(new Error('denied'))
    Object.assign(navigator, { clipboard: { writeText } })

    global.fetch = mockFetchRouter()
    render(<DistributionPage />)
    await screen.findByText('Podcast RSS Feed')

    await userEvent.click(screen.getByRole('button', { name: 'Copy feed URL' }))

    await waitFor(() => expect(showErrorToast).toHaveBeenCalledWith('Failed to copy feed URL'))
  })

  it('regenerates the feed from the card action', async () => {
    const regenerated = { ...feed, last_generated: '2026-02-01T12:00:00Z' }
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/projects/p1/rss-feed/generate' && (init?.method ?? 'GET') === 'POST',
      () => Promise.resolve({ ok: true, json: async () => regenerated })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Podcast RSS Feed')

    await userEvent.click(screen.getByRole('button', { name: /regenerate feed/i }))

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('RSS feed generated'))
  })

  it('generates the feed from the empty state CTA', async () => {
    const fetchMock = withOverride(
      mockFetchRouter({ feedStatus: 404 }),
      (url, init) => url === '/api/proxy/projects/p1/rss-feed/generate' && (init?.method ?? 'GET') === 'POST',
      () => Promise.resolve({ ok: true, json: async () => feed })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('No RSS feed yet')

    await userEvent.click(screen.getByRole('button', { name: 'Generate RSS feed' }))

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('RSS feed generated'))
    expect(await screen.findByText('Podcast RSS Feed')).toBeInTheDocument()
  })

  it('shows a 404 project-not-found toast when generation fails with 404', async () => {
    const fetchMock = withOverride(
      mockFetchRouter({ feedStatus: 404 }),
      (url, init) => url === '/api/proxy/projects/p1/rss-feed/generate' && (init?.method ?? 'GET') === 'POST',
      () => Promise.resolve({ ok: false, status: 404 })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('No RSS feed yet')

    await userEvent.click(screen.getByRole('button', { name: 'Generate RSS feed' }))

    await waitFor(() => expect(showErrorToast).toHaveBeenCalledWith('Project not found'))
  })

  it('on 422 generation failure shows the detail toast and opens the edit metadata dialog', async () => {
    const fetchMock = withOverride(
      mockFetchRouter({ feedStatus: 404 }),
      (url, init) => url === '/api/proxy/projects/p1/rss-feed/generate' && (init?.method ?? 'GET') === 'POST',
      () =>
        Promise.resolve({
          ok: false,
          status: 422,
          json: async () => ({
            detail: "podcast_metadata missing required field: 'show_title'",
          }),
        })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('No RSS feed yet')

    await userEvent.click(screen.getByRole('button', { name: 'Generate RSS feed' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith(
        "Failed to generate RSS feed: podcast_metadata missing required field: 'show_title'"
      )
    )
    expect(await screen.findByText('Edit Podcast Metadata')).toBeInTheDocument()
  })

  it('shows a generic error toast for a non-404/422 generation failure', async () => {
    const fetchMock = withOverride(
      mockFetchRouter({ feedStatus: 404 }),
      (url, init) => url === '/api/proxy/projects/p1/rss-feed/generate' && (init?.method ?? 'GET') === 'POST',
      () => Promise.resolve({ ok: false, status: 500 })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('No RSS feed yet')

    await userEvent.click(screen.getByRole('button', { name: 'Generate RSS feed' }))

    await waitFor(() => expect(showErrorToast).toHaveBeenCalledWith('Failed to generate RSS feed'))
  })

  it('shows a network error toast when generation throws', async () => {
    const fetchMock = withOverride(
      mockFetchRouter({ feedStatus: 404 }),
      (url, init) => url === '/api/proxy/projects/p1/rss-feed/generate' && (init?.method ?? 'GET') === 'POST',
      () => Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('No RSS feed yet')

    await userEvent.click(screen.getByRole('button', { name: 'Generate RSS feed' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to generate RSS feed: Network error')
    )
  })

  it('opens the edit metadata dialog prefilled from the project, and updates metadata on submit', async () => {
    const updatedFeed = { ...feed, last_generated: '2026-03-01T00:00:00Z' }
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/projects/p1/rss-feed' && (init?.method ?? 'GET') === 'PUT',
      () => Promise.resolve({ ok: true, json: async () => updatedFeed })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Podcast RSS Feed')

    await userEvent.click(screen.getByRole('button', { name: /edit podcast metadata/i }))
    expect(screen.getByDisplayValue('My Podcast Show')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/proxy/projects/p1/rss-feed',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({
            podcast_metadata: {
              show_title: 'My Podcast Show',
              author: 'Jane Doe',
              description: 'A great show about things',
              explicit: false,
            },
          }),
        })
      )
    )
    expect(showSuccessToast).toHaveBeenCalledWith('Podcast metadata updated')
    await waitFor(() => expect(screen.queryByText('Edit Podcast Metadata')).not.toBeInTheDocument())
  })

  it('shows the detail toast and keeps the dialog open on a 422 metadata update failure', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/projects/p1/rss-feed' && (init?.method ?? 'GET') === 'PUT',
      () =>
        Promise.resolve({
          ok: false,
          status: 422,
          json: async () => ({ detail: "podcast_metadata missing required field: 'author'" }),
        })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Podcast RSS Feed')

    await userEvent.click(screen.getByRole('button', { name: /edit podcast metadata/i }))
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith(
        "Failed to update podcast metadata: podcast_metadata missing required field: 'author'"
      )
    )
    expect(screen.getByText('Edit Podcast Metadata')).toBeInTheDocument()
  })

  it('shows a project-not-found toast on a 404 metadata update failure', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/projects/p1/rss-feed' && (init?.method ?? 'GET') === 'PUT',
      () => Promise.resolve({ ok: false, status: 404 })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Podcast RSS Feed')

    await userEvent.click(screen.getByRole('button', { name: /edit podcast metadata/i }))
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(showErrorToast).toHaveBeenCalledWith('Project not found'))
  })

  it('shows a generic error toast for a non-404/422 metadata update failure', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/projects/p1/rss-feed' && (init?.method ?? 'GET') === 'PUT',
      () => Promise.resolve({ ok: false, status: 500 })
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Podcast RSS Feed')

    await userEvent.click(screen.getByRole('button', { name: /edit podcast metadata/i }))
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to update podcast metadata')
    )
  })

  it('logs and continues rendering when the project fetch throws (feed still loads)', async () => {
    global.fetch = jest.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      if (url === '/api/proxy/projects/p1' && method === 'GET') {
        return Promise.reject(new Error('boom'))
      }
      if (url === '/api/proxy/projects/p1/rss-feed' && method === 'GET') {
        return Promise.resolve({ ok: true, status: 200, json: async () => feed })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    }) as jest.Mock

    render(<DistributionPage />)

    expect(await screen.findByText('Podcast RSS Feed')).toBeInTheDocument()
  })

  it('shows a network error toast when the metadata update throws', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/projects/p1/rss-feed' && (init?.method ?? 'GET') === 'PUT',
      () => Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock

    render(<DistributionPage />)
    await screen.findByText('Podcast RSS Feed')

    await userEvent.click(screen.getByRole('button', { name: /edit podcast metadata/i }))
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to update podcast metadata: Network error')
    )
  })

  it('renders per-platform validation statuses when present', async () => {
    global.fetch = jest.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      if (url === '/api/proxy/projects/p1' && method === 'GET') {
        return Promise.resolve({ ok: true, json: async () => project })
      }
      if (url === '/api/proxy/projects/p1/rss-feed' && method === 'GET') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            ...feed,
            validation_status: { spotify: 'valid', apple: 'pending' },
          }),
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    }) as jest.Mock

    render(<DistributionPage />)
    await screen.findByText('Podcast RSS Feed')

    expect(screen.getByText('spotify')).toBeInTheDocument()
    expect(screen.getByText('valid')).toBeInTheDocument()
    expect(screen.getByText('apple')).toBeInTheDocument()
    expect(screen.getByText('pending')).toBeInTheDocument()
  })
})
