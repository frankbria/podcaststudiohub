import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DashboardPage from '@/app/(auth)/dashboard/page'
import { withOverride } from '../../../test-utils/fetch-router'

let mockSessionStatus = 'authenticated'

// DashboardPage's load effect depends on the `router` object itself (not just
// `router.push`), so the mock must return the SAME object on every call —
// otherwise every render creates a new reference, retriggering the effect
// and re-fetching projects in an infinite loop that clobbers state updates
// made by other handlers (edit/delete) mid-test.
jest.mock('next/navigation', () => {
  const router = { push: jest.fn() }
  return { useRouter: () => router }
})

const mockPush = (jest.requireMock('next/navigation').useRouter() as { push: jest.Mock }).push

jest.mock('next-auth/react', () => ({
  useSession: () => ({ status: mockSessionStatus }),
}))

jest.mock('@/lib/toast', () => ({
  showSuccessToast: jest.fn(),
  showErrorToast: jest.fn(),
}))

const { showSuccessToast, showErrorToast } = jest.requireMock('@/lib/toast')

const podcastProject = {
  id: '1',
  name: 'My First Podcast',
  description: null,
  episode_count: 2,
  created_at: '2026-01-01',
}

type FetchRouterOpts = {
  projects?: typeof podcastProject[]
  listOk?: boolean
}

function mockFetchRouter({ projects = [podcastProject], listOk = true }: FetchRouterOpts = {}) {
  return jest.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    if (url === '/api/proxy/projects' && method === 'GET') {
      return listOk
        ? Promise.resolve({ ok: true, json: async () => ({ projects }) })
        : Promise.resolve({ ok: false })
    }
    return Promise.resolve({ ok: true, json: async () => ({}) })
  }) as jest.Mock
}

describe('DashboardPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockSessionStatus = 'authenticated'
  })

  it('renders projects on successful load', async () => {
    global.fetch = mockFetchRouter()

    render(<DashboardPage />)

    expect(await screen.findByText('My First Podcast')).toBeInTheDocument()
    expect(global.fetch).toHaveBeenCalledWith('/api/proxy/projects')
  })

  it('shows an error toast when the load fails', async () => {
    global.fetch = mockFetchRouter({ listOk: false })

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

  it('redirects to /login when unauthenticated', async () => {
    mockSessionStatus = 'unauthenticated'
    global.fetch = mockFetchRouter()

    render(<DashboardPage />)

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/login'))
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('shows an empty state when there are no projects', async () => {
    global.fetch = mockFetchRouter({ projects: [] })

    render(<DashboardPage />)

    expect(await screen.findByText('No projects yet')).toBeInTheDocument()
  })

  it('opens the create dialog from the empty state action', async () => {
    global.fetch = mockFetchRouter({ projects: [] })
    render(<DashboardPage />)
    await screen.findByText('No projects yet')

    const createButtons = screen.getAllByRole('button', { name: 'Create Project' })
    await userEvent.click(createButtons[createButtons.length - 1])

    expect(screen.getByLabelText(/project title/i)).toBeInTheDocument()
  })

  it('links the project title to the project page (link, not a role=button card)', async () => {
    global.fetch = mockFetchRouter()
    render(<DashboardPage />)

    const link = await screen.findByRole('link', { name: /open project: my first podcast/i })
    expect(link).toHaveAttribute('href', '/projects/1')
    // the card itself must not masquerade as a button wrapping other controls
    expect(screen.queryByRole('button', { name: /open project: my first podcast/i })).not.toBeInTheDocument()
    // Edit/Delete remain reachable as siblings of the title link
    expect(screen.getByRole('button', { name: 'Edit My First Podcast' })).toBeInTheDocument()
  })

  it('creates a project and reloads the list', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/projects' && (init?.method ?? 'GET') === 'POST', () =>
      Promise.resolve({ ok: true, json: async () => ({}) })
    )
    global.fetch = fetchMock

    render(<DashboardPage />)
    await screen.findByText('My First Podcast')

    await userEvent.click(screen.getByRole('button', { name: 'Create Project' }))
    await userEvent.type(screen.getByLabelText(/project title/i), 'New Show')
    const submitButtons = screen.getAllByRole('button', { name: /create project/i })
    await userEvent.click(submitButtons[submitButtons.length - 1])

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/proxy/projects',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            name: 'New Show',
            description: null,
            podcast_metadata: { language: 'en', explicit: false },
          }),
        })
      )
    })
    expect(showSuccessToast).toHaveBeenCalledWith('Project created successfully')
  })

  it('closes the create dialog without submitting when cancelled', async () => {
    global.fetch = mockFetchRouter()
    render(<DashboardPage />)
    await screen.findByText('My First Podcast')

    await userEvent.click(screen.getByRole('button', { name: 'Create Project' }))
    expect(screen.getByLabelText(/project title/i)).toBeInTheDocument()

    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByLabelText(/project title/i)).not.toBeInTheDocument())
  })

  it('shows an error toast when project creation fails', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/projects' && (init?.method ?? 'GET') === 'POST', () =>
      Promise.resolve({ ok: false, statusText: 'Bad Request' })
    )
    global.fetch = fetchMock

    render(<DashboardPage />)
    await screen.findByText('My First Podcast')
    await userEvent.click(screen.getByRole('button', { name: 'Create Project' }))
    await userEvent.type(screen.getByLabelText(/project title/i), 'New Show')
    const submitButtons = screen.getAllByRole('button', { name: /create project/i })
    await userEvent.click(submitButtons[submitButtons.length - 1])

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to create project: Bad Request')
    )
  })

  it('shows a network error toast when project creation throws', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/projects' && (init?.method ?? 'GET') === 'POST', () =>
      Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock

    render(<DashboardPage />)
    await screen.findByText('My First Podcast')
    await userEvent.click(screen.getByRole('button', { name: 'Create Project' }))
    await userEvent.type(screen.getByLabelText(/project title/i), 'New Show')
    const submitButtons = screen.getAllByRole('button', { name: /create project/i })
    await userEvent.click(submitButtons[submitButtons.length - 1])

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to create project: Network error')
    )
  })

  it('updates a project title', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/projects/1' && (init?.method ?? 'GET') === 'PUT', () =>
      Promise.resolve({ ok: true, json: async () => ({}) })
    )
    global.fetch = fetchMock

    render(<DashboardPage />)
    await screen.findByText('My First Podcast')

    await userEvent.click(screen.getByRole('button', { name: 'Edit My First Podcast' }))
    const titleInput = screen.getByLabelText(/project title/i)
    await userEvent.clear(titleInput)
    await userEvent.type(titleInput, 'Renamed Show')
    await userEvent.click(screen.getByRole('button', { name: 'Update' }))

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('Project updated'))
    expect(await screen.findByText('Renamed Show')).toBeInTheDocument()
  })

  it('shows an error toast when project update fails', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/projects/1' && (init?.method ?? 'GET') === 'PUT', () =>
      Promise.resolve({ ok: false, statusText: 'Bad Request' })
    )
    global.fetch = fetchMock

    render(<DashboardPage />)
    await screen.findByText('My First Podcast')
    await userEvent.click(screen.getByRole('button', { name: 'Edit My First Podcast' }))
    await userEvent.click(screen.getByRole('button', { name: 'Update' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to update project: Bad Request')
    )
  })

  it('shows a network error toast when project update throws', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/projects/1' && (init?.method ?? 'GET') === 'PUT', () =>
      Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock

    render(<DashboardPage />)
    await screen.findByText('My First Podcast')
    await userEvent.click(screen.getByRole('button', { name: 'Edit My First Podcast' }))
    await userEvent.click(screen.getByRole('button', { name: 'Update' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to update project: Network error')
    )
  })

  it('closes the edit dialog without submitting when cancelled', async () => {
    global.fetch = mockFetchRouter()
    render(<DashboardPage />)
    await screen.findByText('My First Podcast')

    await userEvent.click(screen.getByRole('button', { name: 'Edit My First Podcast' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByLabelText(/project title/i)).not.toBeInTheDocument())
  })

  it('deletes a project', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/projects/1' && (init?.method ?? 'GET') === 'DELETE', () =>
      Promise.resolve({ ok: true, json: async () => ({}) })
    )
    global.fetch = fetchMock

    render(<DashboardPage />)
    await screen.findByText('My First Podcast')

    await userEvent.click(screen.getByRole('button', { name: 'Delete My First Podcast' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('Project deleted successfully'))
    expect(screen.queryByText('My First Podcast')).not.toBeInTheDocument()
  })

  it('shows an error toast when project deletion fails', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/projects/1' && (init?.method ?? 'GET') === 'DELETE', () =>
      Promise.resolve({ ok: false, statusText: 'Bad Request' })
    )
    global.fetch = fetchMock

    render(<DashboardPage />)
    await screen.findByText('My First Podcast')
    await userEvent.click(screen.getByRole('button', { name: 'Delete My First Podcast' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to delete project: Bad Request')
    )
  })

  it('shows a network error toast when project deletion throws', async () => {
    const fetchMock = withOverride(mockFetchRouter(), (url, init) => url === '/api/proxy/projects/1' && (init?.method ?? 'GET') === 'DELETE', () =>
      Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock

    render(<DashboardPage />)
    await screen.findByText('My First Podcast')
    await userEvent.click(screen.getByRole('button', { name: 'Delete My First Podcast' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to delete project: Network error')
    )
  })

  it('closes the delete dialog without deleting when cancelled', async () => {
    global.fetch = mockFetchRouter()
    render(<DashboardPage />)
    await screen.findByText('My First Podcast')

    await userEvent.click(screen.getByRole('button', { name: 'Delete My First Podcast' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByText('Delete Project?')).not.toBeInTheDocument())
    expect(screen.getByText('My First Podcast')).toBeInTheDocument()
  })
})
