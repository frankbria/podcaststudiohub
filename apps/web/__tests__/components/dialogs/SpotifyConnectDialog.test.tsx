import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SpotifyConnectDialog } from '@/components/dialogs/SpotifyConnectDialog'

jest.mock('@/lib/toast', () => ({
  showSuccessToast: jest.fn(),
  showErrorToast: jest.fn(),
}))

const { showErrorToast } = jest.requireMock('@/lib/toast')

describe('SpotifyConnectDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders the connect dialog', () => {
    render(<SpotifyConnectDialog {...defaultProps} />)
    expect(screen.getByRole('heading', { name: 'Connect Spotify' })).toBeInTheDocument()
  })

  it('does not render content when closed', () => {
    render(<SpotifyConnectDialog {...defaultProps} open={false} />)
    expect(screen.queryByRole('heading', { name: 'Connect Spotify' })).not.toBeInTheDocument()
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    render(<SpotifyConnectDialog {...defaultProps} />)
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })

  it('fetches an authorize URL and triggers a full-page redirect on success', async () => {
    // jsdom doesn't implement real navigation — window.location.assign logs
    // (but doesn't throw) a "not implemented" jsdomError, which is fine here;
    // we only assert the authorize call happened and no error was surfaced.
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ authorize_url: 'https://accounts.spotify.com/authorize?x=1', state: 's1' }),
    }) as jest.Mock

    render(<SpotifyConnectDialog {...defaultProps} />)
    await userEvent.click(screen.getByRole('button', { name: 'Connect Spotify' }))

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/proxy/distribution-targets/spotify/authorize',
        expect.objectContaining({ method: 'POST' })
      )
    })
    expect(showErrorToast).not.toHaveBeenCalled()
  })

  it('shows a specific error toast on 503 (OAuth not configured)', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 503, statusText: 'Service Unavailable' }) as jest.Mock

    render(<SpotifyConnectDialog {...defaultProps} />)
    await userEvent.click(screen.getByRole('button', { name: 'Connect Spotify' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Spotify OAuth is not configured on the server')
    )
  })

  it('shows a generic error toast on other non-ok responses', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500, statusText: 'Server Error' }) as jest.Mock

    render(<SpotifyConnectDialog {...defaultProps} />)
    await userEvent.click(screen.getByRole('button', { name: 'Connect Spotify' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to start Spotify connection: Server Error')
    )
  })

  it('shows a network error toast when the fetch rejects', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('boom')) as jest.Mock

    render(<SpotifyConnectDialog {...defaultProps} />)
    await userEvent.click(screen.getByRole('button', { name: 'Connect Spotify' }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to start Spotify connection: Network error')
    )
  })
})
