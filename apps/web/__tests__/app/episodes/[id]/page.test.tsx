import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import EpisodePage from '@/app/(auth)/episodes/[id]/page'

const mockPush = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({ id: 'ep1' }),
}))

jest.mock('next-auth/react', () => ({
  useSession: () => ({ status: 'authenticated' }),
}))

jest.mock('@/lib/toast', () => ({
  showSuccessToast: jest.fn(),
  showErrorToast: jest.fn(),
}))

// SSE/polling are only wired up for active statuses; stub them so a draft
// episode render never touches the network manager.
jest.mock('@/lib/event-source-manager', () => ({
  startPolling: jest.fn(() => jest.fn()),
  RobustEventSource: class {
    connect() {}
    close() {}
  },
}))

const { showSuccessToast, showErrorToast } = jest.requireMock('@/lib/toast')

const draftEpisode = {
  id: 'ep1',
  episode_metadata: { title: 'Test Episode', description: 'desc' },
  generation_status: 'draft',
  generation_progress: {},
  s3_url: null,
  project_id: 'p1',
  tts_config_id: null,
  episode_number: 1,
}

// Route the component's mount-time fetches by URL; generate POST is asserted separately.
function mockFetchRouter() {
  return jest.fn((url: string, init?: RequestInit) => {
    if (url.includes('/generate')) {
      return Promise.resolve({ ok: true, json: async () => ({}) })
    }
    if (url.includes('/content/episodes/')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ content_sources: [{ id: 'c1', source_type: 'url', source_data: {}, extraction_status: 'complete' }] }),
      })
    }
    if (url.includes('/tts-configs')) {
      return Promise.resolve({ ok: true, json: async () => ({ configs: [] }) })
    }
    // episode detail
    return Promise.resolve({ ok: true, json: async () => draftEpisode })
  }) as jest.Mock
}

describe('EpisodePage generate flow', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('loads the episode and enables the Generate button', async () => {
    global.fetch = mockFetchRouter()
    render(<EpisodePage />)

    expect(await screen.findByText('Test Episode')).toBeInTheDocument()
    const generateBtn = screen.getByRole('button', { name: /generate podcast/i })
    await waitFor(() => expect(generateBtn).toBeEnabled())
  })

  it('POSTs to the generate endpoint and shows a success toast', async () => {
    const fetchMock = mockFetchRouter()
    global.fetch = fetchMock
    render(<EpisodePage />)

    const generateBtn = await screen.findByRole('button', { name: /generate podcast/i })
    await waitFor(() => expect(generateBtn).toBeEnabled())

    await userEvent.click(generateBtn)

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/proxy/generation/episodes/ep1/generate',
        { method: 'POST' }
      )
    })
    expect(showSuccessToast).toHaveBeenCalledWith('Podcast generation started')
    expect(showErrorToast).not.toHaveBeenCalled()
  })
})
