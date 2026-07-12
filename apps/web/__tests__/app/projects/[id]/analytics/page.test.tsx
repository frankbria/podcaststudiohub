import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ProjectAnalyticsPage from '@/app/(auth)/projects/[id]/analytics/page'

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

const { showErrorToast } = jest.requireMock('@/lib/toast')

const fullAnalytics = {
  project_id: 'p1',
  period: { from: '2026-06-01', to: '2026-07-01', days: 30 },
  summary: { total_downloads: 120, total_plays: 75, total_listen_hours: 45 },
  trends: {
    weekly_downloads: [
      { week: '2026-W22', downloads: 30 },
      { week: '2026-W23', downloads: 90 },
    ],
  },
  top_episodes: [
    { episode_id: 'ep-1', downloads: 60 },
    { episode_id: 'ep-2', downloads: 40 },
  ],
}

const emptyAnalytics = {
  project_id: 'p1',
  period: { from: '2026-06-01', to: '2026-07-01', days: 30 },
  summary: { total_downloads: 0, total_plays: 0, total_listen_hours: 0 },
  trends: { weekly_downloads: [] },
  top_episodes: [],
}

type FetchRouterOpts = {
  analytics?: typeof fullAnalytics
  ok?: boolean
  status?: number
}

function mockFetchRouter({
  analytics = fullAnalytics,
  ok = true,
  status = 200,
}: FetchRouterOpts = {}) {
  return jest.fn((url: string) => {
    if (url.startsWith('/api/proxy/projects/p1/analytics')) {
      return ok
        ? Promise.resolve({ ok: true, status: 200, json: async () => analytics })
        : Promise.resolve({ ok: false, status })
    }
    return Promise.resolve({ ok: true, json: async () => ({}) })
  }) as jest.Mock
}

describe('ProjectAnalyticsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('loads and displays analytics summary, trend, and top episodes', async () => {
    global.fetch = mockFetchRouter()
    render(<ProjectAnalyticsPage />)

    expect(await screen.findByText('120')).toBeInTheDocument()
    expect(screen.getByText('75')).toBeInTheDocument()
    expect(screen.getByText('45')).toBeInTheDocument()
    expect(screen.getByText('2026-W22')).toBeInTheDocument()
    expect(screen.getByText('2026-W23')).toBeInTheDocument()
    expect(screen.getByText('ep-1')).toBeInTheDocument()
    expect(screen.getByText('ep-2')).toBeInTheDocument()
    expect(global.fetch).toHaveBeenCalledWith('/api/proxy/projects/p1/analytics?days=30')
  })

  it('sizes the weekly download bars relative to the max week', async () => {
    global.fetch = mockFetchRouter()
    render(<ProjectAnalyticsPage />)
    await screen.findByText('2026-W23')

    expect(screen.getByTestId('bar-2026-W22')).toHaveStyle({ width: '33.33333333333333%' })
    expect(screen.getByTestId('bar-2026-W23')).toHaveStyle({ width: '100%' })
  })

  it('renders zero-width bars when every week in the trend has zero downloads', async () => {
    global.fetch = mockFetchRouter({
      analytics: {
        ...fullAnalytics,
        trends: { weekly_downloads: [{ week: '2026-W22', downloads: 0 }] },
      },
    })
    render(<ProjectAnalyticsPage />)
    await screen.findByText('2026-W22')

    expect(screen.getByTestId('bar-2026-W22')).toHaveStyle({ width: '0%' })
  })

  it('shows a muted message when the weekly trend is empty but summary has data', async () => {
    global.fetch = mockFetchRouter({
      analytics: { ...fullAnalytics, trends: { weekly_downloads: [] } },
    })
    render(<ProjectAnalyticsPage />)

    expect(await screen.findByText('No downloads in this period')).toBeInTheDocument()
  })

  it('shows a muted message when there are no top episodes', async () => {
    global.fetch = mockFetchRouter({
      analytics: { ...fullAnalytics, top_episodes: [] },
    })
    render(<ProjectAnalyticsPage />)

    expect(await screen.findByText('No episode downloads yet')).toBeInTheDocument()
  })

  it('links each top episode to its episode page', async () => {
    global.fetch = mockFetchRouter()
    render(<ProjectAnalyticsPage />)

    const link = await screen.findByRole('link', { name: 'ep-1' })
    expect(link).toHaveAttribute('href', '/episodes/ep-1')
  })

  it('shows the empty state when summary is all zero and trend is empty', async () => {
    global.fetch = mockFetchRouter({ analytics: emptyAnalytics })
    render(<ProjectAnalyticsPage />)

    expect(await screen.findByText('No analytics yet')).toBeInTheDocument()
    expect(
      screen.getByText('Data appears once episodes are downloaded or played')
    ).toBeInTheDocument()
    expect(screen.queryByText('Top episodes')).not.toBeInTheDocument()
  })

  it('shows a project-not-found empty state on 404', async () => {
    global.fetch = mockFetchRouter({ ok: false, status: 404 })
    render(<ProjectAnalyticsPage />)

    expect(await screen.findByText('Project not found')).toBeInTheDocument()
  })

  it('shows an error toast on a non-2xx, non-404 response', async () => {
    global.fetch = mockFetchRouter({ ok: false, status: 500 })
    render(<ProjectAnalyticsPage />)

    await waitFor(() => expect(showErrorToast).toHaveBeenCalledWith('Failed to load analytics'))
  })

  it('shows a network error toast when the fetch rejects', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('boom')) as jest.Mock
    render(<ProjectAnalyticsPage />)

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to load analytics: Network error')
    )
  })

  it('refetches with the new days value when the period selector changes', async () => {
    const fetchMock = mockFetchRouter()
    global.fetch = fetchMock
    render(<ProjectAnalyticsPage />)
    await screen.findByText('120')

    await userEvent.click(screen.getByRole('combobox', { name: 'Select time period' }))
    await userEvent.click(screen.getByRole('option', { name: '7 days' }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/proxy/projects/p1/analytics?days=7')
    )
  })

  it('navigates back to the project page', async () => {
    global.fetch = mockFetchRouter()
    render(<ProjectAnalyticsPage />)
    await screen.findByText('120')

    await userEvent.click(screen.getByRole('button', { name: '← Back to Project' }))
    expect(mockPush).toHaveBeenCalledWith('/projects/p1')
  })

  it('shows a loading skeleton while fetching', () => {
    global.fetch = jest.fn(() => new Promise(() => {})) as jest.Mock
    render(<ProjectAnalyticsPage />)

    expect(screen.getByLabelText('Loading')).toBeInTheDocument()
  })
})
