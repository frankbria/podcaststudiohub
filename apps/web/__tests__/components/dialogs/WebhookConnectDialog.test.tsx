import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WebhookConnectDialog } from '@/components/dialogs/WebhookConnectDialog'

jest.mock('@/lib/toast', () => ({
  showSuccessToast: jest.fn(),
  showErrorToast: jest.fn(),
}))

const { showErrorToast } = jest.requireMock('@/lib/toast')

describe('WebhookConnectDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: jest.fn(),
    onConnected: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders the connect dialog with POST as the default method', () => {
    render(<WebhookConnectDialog {...defaultProps} />)
    expect(screen.getByText('Connect Webhook')).toBeInTheDocument()
    expect(screen.getByLabelText(/method/i)).toHaveValue('POST')
  })

  it('does not render content when closed', () => {
    render(<WebhookConnectDialog {...defaultProps} open={false} />)
    expect(screen.queryByText('Connect Webhook')).not.toBeInTheDocument()
  })

  it('shows a validation error for a non-https URL', async () => {
    render(<WebhookConnectDialog {...defaultProps} />)
    await userEvent.type(screen.getByLabelText(/name/i), 'My webhook')
    await userEvent.type(screen.getByLabelText(/url/i), 'http://example.com/webhook')
    await userEvent.tab()

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  })

  it('submits name/url/method and calls onConnected on success', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 'dt-2' }) }) as jest.Mock

    render(<WebhookConnectDialog {...defaultProps} />)
    await userEvent.type(screen.getByLabelText(/name/i), 'My webhook')
    await userEvent.type(screen.getByLabelText(/url/i), 'https://example.com/webhook')
    await userEvent.selectOptions(screen.getByLabelText(/method/i), 'GET')
    await userEvent.click(screen.getByRole('button', { name: /^connect$/i }))

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/proxy/distribution-targets/webhook',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            name: 'My webhook',
            url: 'https://example.com/webhook',
            method: 'GET',
          }),
        })
      )
    })
    expect(defaultProps.onConnected).toHaveBeenCalled()
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })

  it('shows an error toast when connecting fails', async () => {
    global.fetch = jest
      .fn()
      .mockResolvedValue({ ok: false, statusText: 'Bad Request', json: async () => ({}) }) as jest.Mock

    render(<WebhookConnectDialog {...defaultProps} />)
    await userEvent.type(screen.getByLabelText(/name/i), 'My webhook')
    await userEvent.type(screen.getByLabelText(/url/i), 'https://example.com/webhook')
    await userEvent.click(screen.getByRole('button', { name: /^connect$/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to connect webhook: Bad Request')
    )
    expect(defaultProps.onConnected).not.toHaveBeenCalled()
  })

  it('surfaces the backend SSRF-guard detail when the URL is rejected with 422', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      statusText: 'Unprocessable Entity',
      json: async () => ({ detail: 'Webhook URL is not allowed: resolves to a private address' }),
    }) as jest.Mock

    render(<WebhookConnectDialog {...defaultProps} />)
    await userEvent.type(screen.getByLabelText(/name/i), 'My webhook')
    await userEvent.type(screen.getByLabelText(/url/i), 'https://internal.example.com/webhook')
    await userEvent.click(screen.getByRole('button', { name: /^connect$/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith(
        'Failed to connect webhook: Webhook URL is not allowed: resolves to a private address'
      )
    )
  })

  it('shows a network error toast when connecting throws', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('boom')) as jest.Mock

    render(<WebhookConnectDialog {...defaultProps} />)
    await userEvent.type(screen.getByLabelText(/name/i), 'My webhook')
    await userEvent.type(screen.getByLabelText(/url/i), 'https://example.com/webhook')
    await userEvent.click(screen.getByRole('button', { name: /^connect$/i }))

    await waitFor(() =>
      expect(showErrorToast).toHaveBeenCalledWith('Failed to connect webhook: Network error')
    )
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    render(<WebhookConnectDialog {...defaultProps} />)
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })
})
