import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import EpisodePage from '@/app/(auth)/episodes/[id]/page'
import { withOverride } from '../../../../test-utils/fetch-router'

const mockPush = jest.fn()
const mockBack = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, back: mockBack }),
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
// episode render never touches the network manager. Tests that need to drive
// the SSE callbacks (complete/failed/status-change/fallback) reach in via
// `lastRobustESOptions`, which the fake class captures on construction.
let lastRobustESOptions: {
  onMessage: (data: unknown) => void
  onError?: (info: { message: string; attempt: number; maxRetries: number }) => void
  onFallbackToPolling?: () => void
  onStatusChange?: (status: string) => void
} | null = null

const startPollingMock = jest.fn((_options?: unknown) => jest.fn())

jest.mock('@/lib/event-source-manager', () => ({
  startPolling: (options: unknown) => startPollingMock(options),
  RobustEventSource: class {
    constructor(_url: string, options: typeof lastRobustESOptions) {
      lastRobustESOptions = options
    }
    connect() {}
    close() {}
  },
}))

const { showSuccessToast, showErrorToast } = jest.requireMock('@/lib/toast')

const draftEpisode = {
  id: 'ep1',
  episode_metadata: { title: 'Test Episode', description: 'desc' },
  generation_status: 'draft',
  generation_progress: {} as { progress?: number; error_message?: string; status?: string },
  s3_url: null as string | null,
  project_id: 'p1',
  tts_config_id: null as string | null,
  episode_number: 1,
}

// In an ACTIVE_STATUSES state so the SSE effect wires up handleMessage /
// handleFallbackToPolling via RobustEventSource.
const generatingEpisode = {
  ...draftEpisode,
  generation_status: 'generating',
}

const failedEpisode = {
  ...draftEpisode,
  generation_status: 'failed',
  generation_progress: { error_message: 'TTS provider rejected the request' },
}

const completeEpisode = {
  ...draftEpisode,
  generation_status: 'complete',
  s3_url: 'https://cdn.example.com/ep1.mp3',
}

// Exercises the "resume in-progress state" branches in loadEpisode: a
// non-null saved tts_config_id and a persisted progress percentage.
const episodeWithSavedProgress = {
  ...draftEpisode,
  generation_status: 'queued',
  generation_progress: { progress: 42 },
  tts_config_id: 'tts1',
}

// Generic router for tests that just need a specific episode/content/tts
// fixture returned, with optional per-endpoint failure overrides layered on.
function mockEpisodeFetchRouter({
  episode = draftEpisode,
  contentSources = [{ id: 'c1', source_type: 'url', source_data: { url: 'https://example.com' }, extraction_status: 'complete' }],
  ttsConfigs = [] as Array<{ id: string; name: string; provider: string; is_default: boolean }>,
}: {
  episode?: typeof draftEpisode
  contentSources?: Array<{ id: string; source_type: string; source_data: Record<string, string>; extraction_status: string }>
  ttsConfigs?: Array<{ id: string; name: string; provider: string; is_default: boolean }>
} = {}) {
  return jest.fn((url: string) => {
    if (url.includes('/generate')) {
      return Promise.resolve({ ok: true, json: async () => ({}) })
    }
    if (/\/api\/proxy\/episodes\/[^/]+\/content(\?|$)/.test(url)) {
      return Promise.resolve({ ok: true, json: async () => ({ content_sources: contentSources }) })
    }
    if (url.includes('/tts-configs')) {
      return Promise.resolve({ ok: true, json: async () => ({ configs: ttsConfigs }) })
    }
    return Promise.resolve({ ok: true, json: async () => episode })
  }) as jest.Mock
}

// Route the component's mount-time fetches by URL; generate POST is asserted separately.
function mockFetchRouter() {
  return jest.fn((url: string, init?: RequestInit) => {
    if (url.includes('/generate')) {
      return Promise.resolve({ ok: true, json: async () => ({}) })
    }
    if (/\/api\/proxy\/episodes\/[^/]+\/content(\?|$)/.test(url)) {
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

// Like mockFetchRouter, but returns a saved TTS config so the Saved
// Configurations <Select> renders (the path that crashed in #299).
function mockFetchRouterWithSavedConfig() {
  return jest.fn((url: string) => {
    if (/\/api\/proxy\/episodes\/[^/]+\/content(\?|$)/.test(url)) {
      return Promise.resolve({ ok: true, json: async () => ({ content_sources: [] }) })
    }
    if (url.includes('/tts-configs')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ configs: [{ id: 'tts1', name: 'My Voice', provider: 'openai', is_default: true }] }),
      })
    }
    return Promise.resolve({ ok: true, json: async () => draftEpisode })
  }) as jest.Mock
}

beforeEach(() => {
  lastRobustESOptions = null
})

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

describe('EpisodePage TTS config selector (#299)', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('opens the saved-config Select and renders "Default (no override)" without crashing', async () => {
    global.fetch = mockFetchRouterWithSavedConfig()
    render(<EpisodePage />)

    await screen.findByText('Test Episode')
    await userEvent.click(screen.getByRole('button', { name: /tts settings/i }))
    // Opening the Select renders the items; the default option previously threw
    // at render via an empty-string SelectItem value (#299).
    await userEvent.click(await screen.findByLabelText(/select a saved tts configuration/i))

    expect(await screen.findByText('Default (no override)')).toBeInTheDocument()
  })

  it('applies the default option as tts_config_id: null', async () => {
    const fetchMock = mockFetchRouterWithSavedConfig()
    global.fetch = fetchMock
    render(<EpisodePage />)

    await screen.findByText('Test Episode')
    await userEvent.click(screen.getByRole('button', { name: /tts settings/i }))
    await userEvent.click(await screen.findByLabelText(/select a saved tts configuration/i))
    await userEvent.click(await screen.findByText('Default (no override)'))
    await userEvent.click(screen.getByRole('button', { name: /apply to episode/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/proxy/episodes/ep1',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ tts_config_id: null }),
        })
      )
    })
  })
})

describe('EpisodePage generate failures', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('shows an error toast when generation fails to start', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter(),
      (url) => url.includes('/generate'),
      () => Promise.resolve({ ok: false, statusText: 'Bad Request' })
    )
    global.fetch = fetchMock
    render(<EpisodePage />)

    const generateBtn = await screen.findByRole('button', { name: /generate podcast/i })
    await waitFor(() => expect(generateBtn).toBeEnabled())
    await userEvent.click(generateBtn)

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to generate podcast: Bad Request')
    )
  })

  it('shows a network error toast when generation throws', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter(),
      (url) => url.includes('/generate'),
      () => Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock
    render(<EpisodePage />)

    const generateBtn = await screen.findByRole('button', { name: /generate podcast/i })
    await waitFor(() => expect(generateBtn).toBeEnabled())
    await userEvent.click(generateBtn)

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to generate podcast: Network error')
    )
  })
})

describe('EpisodePage SSE progress', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('shows the progress bar and connecting status for an active episode', async () => {
    global.fetch = mockEpisodeFetchRouter({ episode: generatingEpisode })
    render(<EpisodePage />)

    await screen.findByText('Test Episode')
    expect(screen.getByRole('progressbar', { name: /generation progress/i })).toBeInTheDocument()
    expect(await screen.findByText('Connecting...')).toBeInTheDocument()
  })

  it('handles a completion message from the SSE stream', async () => {
    global.fetch = mockEpisodeFetchRouter({ episode: generatingEpisode })
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await waitFor(() => expect(lastRobustESOptions).not.toBeNull())
    act(() => {
      lastRobustESOptions!.onMessage({ status: 'complete', progress: { progress: 100 } })
    })

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('Podcast generated successfully'))
  })

  it('handles a failure message from the SSE stream', async () => {
    global.fetch = mockEpisodeFetchRouter({ episode: generatingEpisode })
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await waitFor(() => expect(lastRobustESOptions).not.toBeNull())
    act(() => {
      lastRobustESOptions!.onMessage({ status: 'failed', progress: {} })
    })

    await waitFor(() => expect(showErrorToast).toHaveBeenCalledWith('Podcast generation failed'))
  })

  it('falls back to polling and reflects the polling connection status', async () => {
    global.fetch = mockEpisodeFetchRouter({ episode: generatingEpisode })
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await waitFor(() => expect(lastRobustESOptions).not.toBeNull())
    act(() => {
      lastRobustESOptions!.onFallbackToPolling?.()
    })

    expect(await screen.findByText('Using polling mode')).toBeInTheDocument()
    expect(startPollingMock).toHaveBeenCalled()
  })

  it('reflects connected/reconnecting/error status changes', async () => {
    global.fetch = mockEpisodeFetchRouter({ episode: generatingEpisode })
    render(<EpisodePage />)
    await screen.findByText('Test Episode')
    await waitFor(() => expect(lastRobustESOptions).not.toBeNull())

    act(() => {
      lastRobustESOptions!.onStatusChange?.('connected')
    })
    expect(await screen.findByText('Connected')).toBeInTheDocument()

    act(() => {
      lastRobustESOptions!.onStatusChange?.('reconnecting')
    })
    expect(await screen.findByText('Reconnecting...')).toBeInTheDocument()

    act(() => {
      lastRobustESOptions!.onStatusChange?.('error')
    })
    expect(await screen.findByText('Connection lost, retrying...')).toBeInTheDocument()
  })

  it('prefers a progress-specific status message over the generic one', async () => {
    global.fetch = mockEpisodeFetchRouter({ episode: generatingEpisode })
    render(<EpisodePage />)
    await screen.findByText('Test Episode')
    await waitFor(() => expect(lastRobustESOptions).not.toBeNull())

    // Same status as the current episode ("generating"): the SSE effect keys
    // off episode.generation_status, so keeping it unchanged means it won't
    // restart and reset progressMessage back to the generic STATUS_MESSAGES
    // text, letting us observe the progress-specific message in isolation.
    act(() => {
      lastRobustESOptions!.onMessage({
        status: 'generating',
        progress: { progress: 10, status: 'Generating episode audio (chunk 3 of 10)' },
      })
    })

    expect(await screen.findByText('Generating episode audio (chunk 3 of 10)')).toBeInTheDocument()
  })

  it('logs SSE connection errors via onError', async () => {
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {})
    global.fetch = mockEpisodeFetchRouter({ episode: generatingEpisode })
    render(<EpisodePage />)
    await screen.findByText('Test Episode')
    await waitFor(() => expect(lastRobustESOptions).not.toBeNull())

    act(() => {
      lastRobustESOptions!.onError?.({ message: 'Connection lost, retrying...', attempt: 1, maxRetries: 5 })
    })

    expect(warnSpy).toHaveBeenCalledWith('SSE error: Connection lost, retrying... (attempt 1/5)')
    warnSpy.mockRestore()
  })
})

describe('EpisodePage error and terminal states', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('shows an "episode not found" state when the load fails', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: false }) as jest.Mock
    render(<EpisodePage />)

    expect(await screen.findByText('Episode not found')).toBeInTheDocument()
    expect(showErrorToast).toHaveBeenCalledWith('Failed to load episode')

    await userEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(mockBack).toHaveBeenCalled()
  })

  it('shows a network error toast when the episode fetch rejects', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('boom')) as jest.Mock
    render(<EpisodePage />)

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to load episode: Network error')
    )
  })

  it('shows the failure error message for a failed episode', async () => {
    global.fetch = mockEpisodeFetchRouter({ episode: failedEpisode })
    render(<EpisodePage />)

    expect(await screen.findByText('Error: TTS provider rejected the request')).toBeInTheDocument()
  })

  it('renders the audio player and download button for a completed episode', async () => {
    global.fetch = mockEpisodeFetchRouter({ episode: completeEpisode })
    render(<EpisodePage />)

    await screen.findByText('Test Episode')
    expect(screen.getByLabelText(/podcast audio: test episode/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /download mp3/i })).toBeInTheDocument()
  })

  it('navigates back to the project page', async () => {
    global.fetch = mockEpisodeFetchRouter()
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getByRole('button', { name: '← Back to Project' }))
    expect(mockPush).toHaveBeenCalledWith('/projects/p1')
  })

  it('resumes a saved TTS config id and progress percentage from the loaded episode', async () => {
    global.fetch = mockEpisodeFetchRouter({ episode: episodeWithSavedProgress })
    render(<EpisodePage />)

    await screen.findByText('Test Episode')
    expect(screen.getByRole('progressbar', { name: /generation progress/i })).toHaveAttribute(
      'aria-valuenow',
      '42'
    )
  })
})

describe('EpisodePage content sources', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('adds a URL content source', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter({ contentSources: [] }),
      (url, init) => /\/api\/proxy\/episodes\/[^/]+\/content$/.test(url) && init?.method === 'POST',
      () => Promise.resolve({ ok: true, json: async () => ({}) })
    )
    global.fetch = fetchMock
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getAllByRole('button', { name: 'Add Content' })[0])
    await userEvent.type(
      screen.getByPlaceholderText(/https:\/\/example.com\/article/i),
      'https://example.com/post'
    )
    const submitButtons = screen.getAllByRole('button', { name: /add content/i })
    await userEvent.click(submitButtons[submitButtons.length - 1])

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/proxy/episodes/ep1/content',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            episode_id: 'ep1',
            source_type: 'url',
            source_data: { url: 'https://example.com/post', title: 'Web Article' },
          }),
        })
      )
    })
    expect(showSuccessToast).toHaveBeenCalledWith('Content source added')
  })

  it('adds a text content source', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter({ contentSources: [] }),
      (url, init) => /\/api\/proxy\/episodes\/[^/]+\/content$/.test(url) && init?.method === 'POST',
      () => Promise.resolve({ ok: true, json: async () => ({}) })
    )
    global.fetch = fetchMock
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getAllByRole('button', { name: 'Add Content' })[0])
    await userEvent.click(screen.getByRole('button', { name: 'Text' }))
    await userEvent.type(
      screen.getByPlaceholderText(/enter your content here/i),
      'This is enough content to pass validation.'
    )
    const submitButtons = screen.getAllByRole('button', { name: /add content/i })
    await userEvent.click(submitButtons[submitButtons.length - 1])

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/proxy/episodes/ep1/content',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            episode_id: 'ep1',
            source_type: 'text',
            source_data: { content: 'This is enough content to pass validation.', title: 'Custom Text' },
          }),
        })
      )
    })
  })

  it('opens the add-content dialog from the empty state action', async () => {
    global.fetch = mockEpisodeFetchRouter({ contentSources: [] })
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    const addButtons = screen.getAllByRole('button', { name: 'Add Content' })
    await userEvent.click(addButtons[addButtons.length - 1])

    expect(screen.getByPlaceholderText(/https:\/\/example.com\/article/i)).toBeInTheDocument()
  })

  it('toggles the content source type back to URL', async () => {
    global.fetch = mockEpisodeFetchRouter({ contentSources: [] })
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getAllByRole('button', { name: 'Add Content' })[0])
    await userEvent.click(screen.getByRole('button', { name: 'Text' }))
    await userEvent.click(screen.getByRole('button', { name: 'URL' }))

    expect(screen.getByPlaceholderText(/https:\/\/example.com\/article/i)).toBeInTheDocument()
  })

  it('closes the add-content dialog without submitting when cancelled', async () => {
    global.fetch = mockEpisodeFetchRouter({ contentSources: [] })
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getAllByRole('button', { name: 'Add Content' })[0])
    expect(screen.getByPlaceholderText(/https:\/\/example.com\/article/i)).toBeInTheDocument()

    await userEvent.keyboard('{Escape}')
    await waitFor(() =>
      expect(screen.queryByPlaceholderText(/https:\/\/example.com\/article/i)).not.toBeInTheDocument()
    )
  })

  it('shows an error toast when adding content fails', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter({ contentSources: [] }),
      (url, init) => /\/api\/proxy\/episodes\/[^/]+\/content$/.test(url) && init?.method === 'POST',
      () => Promise.resolve({ ok: false, statusText: 'Bad Request' })
    )
    global.fetch = fetchMock
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getAllByRole('button', { name: 'Add Content' })[0])
    await userEvent.type(
      screen.getByPlaceholderText(/https:\/\/example.com\/article/i),
      'https://example.com/post'
    )
    const submitButtons = screen.getAllByRole('button', { name: /add content/i })
    await userEvent.click(submitButtons[submitButtons.length - 1])

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to add content source: Bad Request')
    )
  })

  it('shows a network error toast when adding content throws', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter({ contentSources: [] }),
      (url, init) => /\/api\/proxy\/episodes\/[^/]+\/content$/.test(url) && init?.method === 'POST',
      () => Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getAllByRole('button', { name: 'Add Content' })[0])
    await userEvent.type(
      screen.getByPlaceholderText(/https:\/\/example.com\/article/i),
      'https://example.com/post'
    )
    const submitButtons = screen.getAllByRole('button', { name: /add content/i })
    await userEvent.click(submitButtons[submitButtons.length - 1])

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to add content source: Network error')
    )
  })

  it('deletes a content source', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter(),
      (url, init) => url === '/api/proxy/content/c1' && init?.method === 'DELETE',
      () => Promise.resolve({ ok: true, json: async () => ({}) })
    )
    global.fetch = fetchMock
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getByRole('button', { name: 'Delete content source' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('Content source deleted'))
  })

  it('shows an error toast when deleting a content source fails', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter(),
      (url, init) => url === '/api/proxy/content/c1' && init?.method === 'DELETE',
      () => Promise.resolve({ ok: false, statusText: 'Bad Request' })
    )
    global.fetch = fetchMock
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getByRole('button', { name: 'Delete content source' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to delete content source: Bad Request')
    )
  })

  it('shows a network error toast when deleting a content source throws', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter(),
      (url, init) => url === '/api/proxy/content/c1' && init?.method === 'DELETE',
      () => Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getByRole('button', { name: 'Delete content source' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to delete content source: Network error')
    )
  })

  it('closes the delete-content dialog without deleting when cancelled', async () => {
    global.fetch = mockEpisodeFetchRouter()
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getByRole('button', { name: 'Delete content source' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByText('Delete Content Source?')).not.toBeInTheDocument())
  })
})

describe('EpisodePage TTS config creation', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('saves a new OpenAI TTS configuration', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter(),
      (url, init) => url === '/api/proxy/tts-configs' && init?.method === 'POST',
      () => Promise.resolve({
        ok: true,
        json: async () => ({ id: 'tts-new', name: 'My Config', provider: 'openai', is_default: false }),
      })
    )
    global.fetch = fetchMock
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getByRole('button', { name: /tts settings/i }))
    await userEvent.type(screen.getByLabelText('Name'), 'My Config')
    await userEvent.click(screen.getByRole('button', { name: 'Save Configuration' }))

    await waitFor(() =>
      expect(showSuccessToast).toHaveBeenCalledWith('TTS configuration saved')
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/proxy/tts-configs',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          name: 'My Config',
          provider: 'openai',
          config: { model: 'tts-1-hd', voice_1: 'alloy', voice_2: 'echo' },
          is_default: false,
        }),
      })
    )
  })

  it('requires voice IDs before an ElevenLabs configuration can be saved', async () => {
    global.fetch = mockEpisodeFetchRouter()
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getByRole('button', { name: /tts settings/i }))
    await userEvent.type(screen.getByLabelText('Name'), 'My ElevenLabs Config')
    await userEvent.click(screen.getByLabelText(/select tts provider/i))
    await userEvent.click(await screen.findByText('ElevenLabs'))

    const saveBtn = screen.getByRole('button', { name: 'Save Configuration' })
    expect(saveBtn).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Voice 1 ID'), 'voice-1')
    expect(saveBtn).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Voice 2 ID'), 'voice-2')
    expect(saveBtn).toBeEnabled()
  })

  it('saves a new ElevenLabs TTS configuration with voice IDs', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter(),
      (url, init) => url === '/api/proxy/tts-configs' && init?.method === 'POST',
      () => Promise.resolve({
        ok: true,
        json: async () => ({ id: 'tts-new', name: 'My ElevenLabs Config', provider: 'elevenlabs', is_default: false }),
      })
    )
    global.fetch = fetchMock
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getByRole('button', { name: /tts settings/i }))
    await userEvent.type(screen.getByLabelText('Name'), 'My ElevenLabs Config')
    await userEvent.click(screen.getByLabelText(/select tts provider/i))
    await userEvent.click(await screen.findByText('ElevenLabs'))
    await userEvent.type(screen.getByLabelText('Voice 1 ID'), 'voice-1')
    await userEvent.type(screen.getByLabelText('Voice 2 ID'), 'voice-2')
    await userEvent.click(screen.getByRole('button', { name: 'Save Configuration' }))

    await waitFor(() => expect(showSuccessToast).toHaveBeenCalledWith('TTS configuration saved'))
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/proxy/tts-configs',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          name: 'My ElevenLabs Config',
          provider: 'elevenlabs',
          config: {
            model: 'eleven_multilingual_v2',
            voice_1_id: 'voice-1',
            voice_2_id: 'voice-2',
          },
          is_default: false,
        }),
      })
    )
  })

  it('shows an error toast when saving a TTS configuration fails', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter(),
      (url, init) => url === '/api/proxy/tts-configs' && init?.method === 'POST',
      () => Promise.resolve({ ok: false })
    )
    global.fetch = fetchMock
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getByRole('button', { name: /tts settings/i }))
    await userEvent.type(screen.getByLabelText('Name'), 'My Config')
    await userEvent.click(screen.getByRole('button', { name: 'Save Configuration' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to save TTS configuration')
    )
  })

  it('shows a network error toast when saving a TTS configuration throws', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter(),
      (url, init) => url === '/api/proxy/tts-configs' && init?.method === 'POST',
      () => Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getByRole('button', { name: /tts settings/i }))
    await userEvent.type(screen.getByLabelText('Name'), 'My Config')
    await userEvent.click(screen.getByRole('button', { name: 'Save Configuration' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to save TTS configuration: Network error')
    )
  })

  it('applies a non-default saved TTS configuration', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter({
        ttsConfigs: [{ id: 'tts1', name: 'My Voice', provider: 'openai', is_default: false }],
      }),
      (url, init) => url === '/api/proxy/episodes/ep1' && init?.method === 'PUT',
      () => Promise.resolve({ ok: true, json: async () => ({}) })
    )
    global.fetch = fetchMock
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getByRole('button', { name: /tts settings/i }))
    await userEvent.click(await screen.findByLabelText(/select a saved tts configuration/i))
    await userEvent.click(await screen.findByText(/my voice \(openai\)/i))
    await userEvent.click(screen.getByRole('button', { name: /apply to episode/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/proxy/episodes/ep1',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ tts_config_id: 'tts1' }),
        })
      )
    })
    expect(showSuccessToast).toHaveBeenCalledWith('TTS settings applied')
  })

  it('shows an error toast when applying TTS settings fails', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter(),
      (url, init) => url === '/api/proxy/episodes/ep1' && init?.method === 'PUT',
      () => Promise.resolve({ ok: false })
    )
    global.fetch = fetchMock
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getByRole('button', { name: /tts settings/i }))
    await userEvent.click(screen.getByRole('button', { name: /apply to episode/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to apply TTS settings')
    )
  })

  it('shows a network error toast when applying TTS settings throws', async () => {
    const fetchMock = withOverride(
      mockEpisodeFetchRouter(),
      (url, init) => url === '/api/proxy/episodes/ep1' && init?.method === 'PUT',
      () => Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock
    render(<EpisodePage />)
    await screen.findByText('Test Episode')

    await userEvent.click(screen.getByRole('button', { name: /tts settings/i }))
    await userEvent.click(screen.getByRole('button', { name: /apply to episode/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to apply TTS settings: Network error')
    )
  })
})
