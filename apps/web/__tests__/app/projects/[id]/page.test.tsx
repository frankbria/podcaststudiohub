import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ProjectPage from '@/app/(auth)/projects/[id]/page'
import { withOverride } from '../../../../test-utils/fetch-router'

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

const project = { id: 'p1', name: 'My Podcast', description: 'A show' }

const pilotEpisode = {
  id: 'e1',
  episode_metadata: { title: 'Pilot', description: 'First one' as string | null },
  generation_status: 'draft',
  created_at: '2026-01-01',
}

// Exercises the getStatusBadge fallback branch (status not in the known map).
const oddEpisode = {
  id: 'e2',
  episode_metadata: { title: 'Bonus', description: null },
  generation_status: 'mystery-status',
  created_at: '2026-01-02',
}

type FetchRouterOpts = {
  episodes?: typeof pilotEpisode[]
  projectOk?: boolean
  episodesOk?: boolean
}

// Routes the component's mount-time GETs by URL. Individual tests layer
// method-specific overrides (PUT/POST/DELETE) on top via mockImplementation.
function mockFetchRouter({
  episodes = [pilotEpisode],
  projectOk = true,
  episodesOk = true,
}: FetchRouterOpts = {}) {
  return jest.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    if (url === '/api/proxy/projects/p1' && method === 'GET') {
      return projectOk
        ? Promise.resolve({ ok: true, json: async () => project })
        : Promise.resolve({ ok: false })
    }
    if (url.startsWith('/api/proxy/episodes?project_id=') && method === 'GET') {
      return episodesOk
        ? Promise.resolve({ ok: true, json: async () => ({ episodes }) })
        : Promise.resolve({ ok: false })
    }
    return Promise.resolve({ ok: true, json: async () => ({}) })
  }) as jest.Mock
}

describe('ProjectPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('loads the project and its episodes', async () => {
    global.fetch = mockFetchRouter({ episodes: [pilotEpisode, oddEpisode] })
    render(<ProjectPage />)

    expect(await screen.findByRole('heading', { name: 'My Podcast' })).toBeInTheDocument()
    expect(screen.getByText('Pilot')).toBeInTheDocument()
    expect(screen.getByLabelText('Status: draft')).toBeInTheDocument()
    expect(screen.getByLabelText('Status: mystery-status')).toBeInTheDocument()
    expect(global.fetch).toHaveBeenCalledWith('/api/proxy/projects/p1')
  })

  it('shows an empty state when there are no episodes', async () => {
    global.fetch = mockFetchRouter({ episodes: [] })
    render(<ProjectPage />)

    expect(await screen.findByText('No episodes in this project')).toBeInTheDocument()
  })

  it('opens the create dialog from the empty state action', async () => {
    global.fetch = mockFetchRouter({ episodes: [] })
    render(<ProjectPage />)
    await screen.findByText('No episodes in this project')

    const createButtons = screen.getAllByRole('button', { name: 'Create Episode' })
    await userEvent.click(createButtons[createButtons.length - 1])

    expect(screen.getByLabelText(/episode title/i)).toBeInTheDocument()
  })

  it('navigates back to the dashboard', async () => {
    global.fetch = mockFetchRouter()
    render(<ProjectPage />)
    await screen.findByText('Pilot')

    await userEvent.click(screen.getByRole('button', { name: '← Back to Dashboard' }))
    expect(mockPush).toHaveBeenCalledWith('/dashboard')
  })

  it('shows sub-nav links to the analytics and distribution pages', async () => {
    global.fetch = mockFetchRouter()
    render(<ProjectPage />)
    await screen.findByText('Pilot')

    expect(screen.getByRole('link', { name: /analytics/i })).toHaveAttribute(
      'href',
      '/projects/p1/analytics'
    )
    expect(screen.getByRole('link', { name: /distribution/i })).toHaveAttribute(
      'href',
      '/projects/p1/distribution'
    )
  })

  it('shows an error toast when the project fails to load', async () => {
    global.fetch = mockFetchRouter({ projectOk: false })
    render(<ProjectPage />)

    await waitFor(() => expect(showErrorToast).toHaveBeenCalledWith('Failed to load project'))
  })

  it('shows an error toast when episodes fail to load', async () => {
    global.fetch = mockFetchRouter({ episodesOk: false })
    render(<ProjectPage />)

    await waitFor(() => expect(showErrorToast).toHaveBeenCalledWith('Failed to load episodes'))
  })

  it('shows a network error toast when the project fetch rejects', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('boom')) as jest.Mock
    render(<ProjectPage />)

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to load project: Network error')
    )
  })

  it('navigates to the episode page when a card is clicked', async () => {
    global.fetch = mockFetchRouter()
    render(<ProjectPage />)

    await userEvent.click(await screen.findByRole('button', { name: /open episode: pilot/i }))
    expect(mockPush).toHaveBeenCalledWith('/episodes/e1')
  })

  it('navigates to the episode page on Enter key', async () => {
    global.fetch = mockFetchRouter()
    render(<ProjectPage />)

    const card = await screen.findByRole('button', { name: /open episode: pilot/i })
    card.focus()
    await userEvent.keyboard('{Enter}')
    expect(mockPush).toHaveBeenCalledWith('/episodes/e1')
  })

  it('creates an episode and navigates to it', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/episodes' && (init?.method ?? 'GET') === 'POST', () =>
      Promise.resolve({ ok: true, json: async () => ({ id: 'new-ep' }) })
    )
    global.fetch = fetchMock

    render(<ProjectPage />)
    await screen.findByText('Pilot')

    await userEvent.click(screen.getByRole('button', { name: 'Create Episode' }))
    await userEvent.type(screen.getByLabelText(/episode title/i), 'New Episode')
    const submitButtons = screen.getAllByRole('button', { name: /create episode/i })
    await userEvent.click(submitButtons[submitButtons.length - 1])

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/proxy/episodes',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            project_id: 'p1',
            episode_metadata: { title: 'New Episode' },
          }),
        })
      )
    })
    expect(showSuccessToast).toHaveBeenCalledWith('Episode created successfully')
    expect(mockPush).toHaveBeenCalledWith('/episodes/new-ep')
  })

  it('closes the create dialog without submitting when cancelled', async () => {
    global.fetch = mockFetchRouter()
    render(<ProjectPage />)
    await screen.findByText('Pilot')

    await userEvent.click(screen.getByRole('button', { name: 'Create Episode' }))
    expect(screen.getByLabelText(/episode title/i)).toBeInTheDocument()

    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByLabelText(/episode title/i)).not.toBeInTheDocument())
  })

  it('shows an error toast when episode creation fails', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/episodes' && (init?.method ?? 'GET') === 'POST', () =>
      Promise.resolve({ ok: false, statusText: 'Bad Request' })
    )
    global.fetch = fetchMock

    render(<ProjectPage />)
    await screen.findByText('Pilot')
    await userEvent.click(screen.getByRole('button', { name: 'Create Episode' }))
    await userEvent.type(screen.getByLabelText(/episode title/i), 'New Episode')
    const submitButtons = screen.getAllByRole('button', { name: /create episode/i })
    await userEvent.click(submitButtons[submitButtons.length - 1])

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to create episode: Bad Request')
    )
  })

  it('shows a network error toast when episode creation throws', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/episodes' && (init?.method ?? 'GET') === 'POST', () =>
      Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock

    render(<ProjectPage />)
    await screen.findByText('Pilot')
    await userEvent.click(screen.getByRole('button', { name: 'Create Episode' }))
    await userEvent.type(screen.getByLabelText(/episode title/i), 'New Episode')
    const submitButtons = screen.getAllByRole('button', { name: /create episode/i })
    await userEvent.click(submitButtons[submitButtons.length - 1])

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to create episode: Network error')
    )
  })

  it('updates the project title', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/projects/p1' && (init?.method ?? 'GET') === 'PUT', () =>
      Promise.resolve({ ok: true, json: async () => ({}) })
    )
    global.fetch = fetchMock

    render(<ProjectPage />)
    await screen.findByRole('heading', { name: 'My Podcast' })

    await userEvent.click(screen.getByRole('button', { name: 'Edit project' }))
    const titleInput = screen.getByLabelText(/project title/i)
    await userEvent.clear(titleInput)
    await userEvent.type(titleInput, 'Renamed Podcast')
    await userEvent.click(screen.getByRole('button', { name: 'Update' }))

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('Project updated'))
    expect(await screen.findByRole('heading', { name: 'Renamed Podcast' })).toBeInTheDocument()
  })

  it('shows an error toast when project update fails', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/projects/p1' && (init?.method ?? 'GET') === 'PUT', () =>
      Promise.resolve({ ok: false, statusText: 'Bad Request' })
    )
    global.fetch = fetchMock

    render(<ProjectPage />)
    await screen.findByRole('heading', { name: 'My Podcast' })
    await userEvent.click(screen.getByRole('button', { name: 'Edit project' }))
    await userEvent.click(screen.getByRole('button', { name: 'Update' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to update project: Bad Request')
    )
  })

  it('shows a network error toast when project update throws', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/projects/p1' && (init?.method ?? 'GET') === 'PUT', () =>
      Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock

    render(<ProjectPage />)
    await screen.findByRole('heading', { name: 'My Podcast' })
    await userEvent.click(screen.getByRole('button', { name: 'Edit project' }))
    await userEvent.click(screen.getByRole('button', { name: 'Update' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to update project: Network error')
    )
  })

  it('closes the edit-project dialog without submitting when cancelled', async () => {
    global.fetch = mockFetchRouter()
    render(<ProjectPage />)
    await screen.findByRole('heading', { name: 'My Podcast' })

    await userEvent.click(screen.getByRole('button', { name: 'Edit project' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByLabelText(/project title/i)).not.toBeInTheDocument())
  })

  it('updates an episode title', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/episodes/e1' && (init?.method ?? 'GET') === 'PUT', () =>
      Promise.resolve({ ok: true, json: async () => ({}) })
    )
    global.fetch = fetchMock

    render(<ProjectPage />)
    await screen.findByText('Pilot')

    await userEvent.click(screen.getByRole('button', { name: 'Edit Pilot' }))
    const titleInput = screen.getByLabelText(/episode title/i)
    await userEvent.clear(titleInput)
    await userEvent.type(titleInput, 'Renamed Episode')
    await userEvent.click(screen.getByRole('button', { name: 'Update' }))

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('Episode updated'))
    expect(await screen.findByText('Renamed Episode')).toBeInTheDocument()
  })

  it('shows an error toast when episode update fails', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/episodes/e1' && (init?.method ?? 'GET') === 'PUT', () =>
      Promise.resolve({ ok: false, statusText: 'Bad Request' })
    )
    global.fetch = fetchMock

    render(<ProjectPage />)
    await screen.findByText('Pilot')
    await userEvent.click(screen.getByRole('button', { name: 'Edit Pilot' }))
    await userEvent.click(screen.getByRole('button', { name: 'Update' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to update episode: Bad Request')
    )
  })

  it('shows a network error toast when episode update throws', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/episodes/e1' && (init?.method ?? 'GET') === 'PUT', () =>
      Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock

    render(<ProjectPage />)
    await screen.findByText('Pilot')
    await userEvent.click(screen.getByRole('button', { name: 'Edit Pilot' }))
    await userEvent.click(screen.getByRole('button', { name: 'Update' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to update episode: Network error')
    )
  })

  it('closes the edit-episode dialog without submitting when cancelled', async () => {
    global.fetch = mockFetchRouter()
    render(<ProjectPage />)
    await screen.findByText('Pilot')

    await userEvent.click(screen.getByRole('button', { name: 'Edit Pilot' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByLabelText(/episode title/i)).not.toBeInTheDocument())
  })

  it('deletes an episode', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/episodes/e1' && (init?.method ?? 'GET') === 'DELETE', () =>
      Promise.resolve({ ok: true, json: async () => ({}) })
    )
    global.fetch = fetchMock

    render(<ProjectPage />)
    await screen.findByText('Pilot')

    await userEvent.click(screen.getByRole('button', { name: 'Delete Pilot' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('Episode deleted successfully'))
    expect(screen.queryByText('Pilot')).not.toBeInTheDocument()
  })

  it('shows an error toast when episode deletion fails', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/episodes/e1' && (init?.method ?? 'GET') === 'DELETE', () =>
      Promise.resolve({ ok: false, statusText: 'Bad Request' })
    )
    global.fetch = fetchMock

    render(<ProjectPage />)
    await screen.findByText('Pilot')
    await userEvent.click(screen.getByRole('button', { name: 'Delete Pilot' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to delete episode: Bad Request')
    )
  })

  it('shows a network error toast when episode deletion throws', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/episodes/e1' && (init?.method ?? 'GET') === 'DELETE', () =>
      Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock

    render(<ProjectPage />)
    await screen.findByText('Pilot')
    await userEvent.click(screen.getByRole('button', { name: 'Delete Pilot' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to delete episode: Network error')
    )
  })

  it('closes the delete-episode dialog without deleting when cancelled', async () => {
    global.fetch = mockFetchRouter()
    render(<ProjectPage />)
    await screen.findByText('Pilot')

    await userEvent.click(screen.getByRole('button', { name: 'Delete Pilot' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByText('Delete Episode?')).not.toBeInTheDocument())
    expect(screen.getByText('Pilot')).toBeInTheDocument()
  })
})
