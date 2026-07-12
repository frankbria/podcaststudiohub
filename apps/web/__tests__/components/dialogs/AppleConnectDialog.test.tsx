import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AppleConnectDialog } from '@/components/dialogs/AppleConnectDialog'
import { withOverride } from '../../../test-utils/fetch-router'

jest.mock('@/lib/toast', () => ({
  showSuccessToast: jest.fn(),
  showErrorToast: jest.fn(),
}))

const { showErrorToast } = jest.requireMock('@/lib/toast')

// Mirrors the real AppleAuthorizeResponse: message is prose, setup_instructions is a URL.
const authorizeInfo = {
  message:
    'Apple Podcasts requires a manually generated API key from Podcasts Connect. ' +
    'Follow the setup instructions to obtain your API key.',
  podcasts_connect_url: 'https://podcastsconnect.apple.com/',
  setup_instructions: 'https://help.apple.com/itc/podcasts_connect/#/itcb54353390',
}

function mockFetchRouter({ authorizeOk = true }: { authorizeOk?: boolean } = {}) {
  return jest.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    if (url === '/api/proxy/distribution-targets/apple/authorize' && method === 'POST') {
      return authorizeOk
        ? Promise.resolve({ ok: true, json: async () => authorizeInfo })
        : Promise.resolve({ ok: false, statusText: 'Server Error' })
    }
    return Promise.resolve({ ok: true, json: async () => ({}) })
  }) as jest.Mock
}

describe('AppleConnectDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: jest.fn(),
    onConnected: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders the connect dialog and fetches setup instructions on open', async () => {
    global.fetch = mockFetchRouter()
    render(<AppleConnectDialog {...defaultProps} />)

    expect(screen.getByText('Connect Apple Podcasts')).toBeInTheDocument()
    // message is the instructional prose; setup_instructions is a help-doc URL
    expect(await screen.findByText(authorizeInfo.message)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /view setup instructions/i })).toHaveAttribute(
      'href',
      authorizeInfo.setup_instructions
    )
    expect(screen.getByRole('link', { name: /open apple podcasts connect/i })).toHaveAttribute(
      'href',
      authorizeInfo.podcasts_connect_url
    )
  })

  it('does not render content when closed', () => {
    global.fetch = mockFetchRouter()
    render(<AppleConnectDialog {...defaultProps} open={false} />)
    expect(screen.queryByText('Connect Apple Podcasts')).not.toBeInTheDocument()
  })

  it('shows an error toast when instructions fail to load', async () => {
    global.fetch = mockFetchRouter({ authorizeOk: false })
    render(<AppleConnectDialog {...defaultProps} />)

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to load Apple Podcasts setup instructions')
    )
  })

  it('shows a network error toast when the instructions fetch rejects', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('boom')) as jest.Mock
    render(<AppleConnectDialog {...defaultProps} />)

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith(
        'Failed to load Apple Podcasts setup instructions: Network error'
      )
    )
  })

  it('shows a validation error when show ID is cleared', async () => {
    global.fetch = mockFetchRouter()
    render(<AppleConnectDialog {...defaultProps} />)
    await screen.findByText(authorizeInfo.message)

    const showIdInput = screen.getByLabelText(/show id/i)
    await userEvent.type(showIdInput, '123')
    await userEvent.clear(showIdInput)

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  })

  it('submits show_id/api_key and calls onConnected on success', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/apple' && (init?.method ?? 'GET') === 'POST',
      () => Promise.resolve({ ok: true, json: async () => ({ id: 'dt-1' }) })
    )
    global.fetch = fetchMock

    render(<AppleConnectDialog {...defaultProps} />)
    await screen.findByText(authorizeInfo.message)

    await userEvent.type(screen.getByLabelText(/show id/i), '12345')
    await userEvent.type(screen.getByLabelText(/api key/i), 'secret-key')
    await userEvent.click(screen.getByRole('button', { name: /^connect$/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/proxy/distribution-targets/apple',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ show_id: '12345', api_key: 'secret-key' }),
        })
      )
    })
    expect(defaultProps.onConnected).toHaveBeenCalled()
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })

  it('shows an error toast when connecting fails', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/apple' && (init?.method ?? 'GET') === 'POST',
      () => Promise.resolve({ ok: false, statusText: 'Bad Request', json: async () => ({}) })
    )
    global.fetch = fetchMock

    render(<AppleConnectDialog {...defaultProps} />)
    await screen.findByText(authorizeInfo.message)

    await userEvent.type(screen.getByLabelText(/show id/i), '12345')
    await userEvent.type(screen.getByLabelText(/api key/i), 'secret-key')
    await userEvent.click(screen.getByRole('button', { name: /^connect$/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to connect Apple Podcasts: Bad Request')
    )
    expect(defaultProps.onConnected).not.toHaveBeenCalled()
  })

  it('surfaces the backend detail message when connecting fails with 422', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/apple' && (init?.method ?? 'GET') === 'POST',
      () =>
        Promise.resolve({
          ok: false,
          statusText: 'Unprocessable Entity',
          json: async () => ({ detail: 'Invalid Apple Podcasts credentials' }),
        })
    )
    global.fetch = fetchMock

    render(<AppleConnectDialog {...defaultProps} />)
    await screen.findByText(authorizeInfo.message)

    await userEvent.type(screen.getByLabelText(/show id/i), '12345')
    await userEvent.type(screen.getByLabelText(/api key/i), 'secret-key')
    await userEvent.click(screen.getByRole('button', { name: /^connect$/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith(
        'Failed to connect Apple Podcasts: Invalid Apple Podcasts credentials'
      )
    )
  })

  it('shows a network error toast when connecting throws', async () => {
    const fetchMock = withOverride(
      mockFetchRouter(),
      (url, init) => url === '/api/proxy/distribution-targets/apple' && (init?.method ?? 'GET') === 'POST',
      () => Promise.reject(new Error('boom'))
    )
    global.fetch = fetchMock

    render(<AppleConnectDialog {...defaultProps} />)
    await screen.findByText(authorizeInfo.message)

    await userEvent.type(screen.getByLabelText(/show id/i), '12345')
    await userEvent.type(screen.getByLabelText(/api key/i), 'secret-key')
    await userEvent.click(screen.getByRole('button', { name: /^connect$/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to connect Apple Podcasts: Network error')
    )
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    global.fetch = mockFetchRouter()
    render(<AppleConnectDialog {...defaultProps} />)
    await screen.findByText(authorizeInfo.message)

    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })
})
