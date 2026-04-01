import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { DownloadButton } from '@/components/DownloadButton'
import * as downloadLib from '@/lib/download'

jest.mock('@/lib/download', () => ({
  sanitizeFilename: jest.fn((title: string) => `${title.toLowerCase().replace(/\s/g, '_')}.mp3`),
  downloadAudioFile: jest.fn(),
}))

describe('DownloadButton', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders Download MP3 button when audioUrl is provided', () => {
    render(
      <DownloadButton
        audioUrl="https://example.com/audio.mp3"
        episodeTitle="Test Episode"
      />
    )
    expect(screen.getByRole('button', { name: /download mp3/i })).toBeInTheDocument()
  })

  it('is disabled when audioUrl is null', () => {
    render(
      <DownloadButton audioUrl={null} episodeTitle="Test Episode" />
    )
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('is disabled when audioUrl is undefined', () => {
    render(
      <DownloadButton audioUrl={undefined} episodeTitle="Test Episode" />
    )
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('is disabled when isLoading is true', () => {
    render(
      <DownloadButton
        audioUrl="https://example.com/audio.mp3"
        episodeTitle="Test Episode"
        isLoading={true}
      />
    )
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('calls downloadAudioFile with sanitized filename on click', async () => {
    const mockDownload = jest.mocked(downloadLib.downloadAudioFile)
    mockDownload.mockResolvedValue(undefined)

    const user = userEvent.setup()
    render(
      <DownloadButton
        audioUrl="https://example.com/audio.mp3"
        episodeTitle="My Episode"
      />
    )

    await user.click(screen.getByRole('button', { name: /download mp3/i }))

    await waitFor(() => {
      expect(mockDownload).toHaveBeenCalledWith(
        'https://example.com/audio.mp3',
        'my_episode.mp3'
      )
    })
  })

  it('shows downloading state while download is in progress', async () => {
    let resolveDownload!: () => void
    const mockDownload = jest.mocked(downloadLib.downloadAudioFile)
    mockDownload.mockReturnValue(
      new Promise<void>((resolve) => {
        resolveDownload = resolve
      })
    )

    const user = userEvent.setup()
    render(
      <DownloadButton
        audioUrl="https://example.com/audio.mp3"
        episodeTitle="My Episode"
      />
    )

    await user.click(screen.getByRole('button', { name: /download mp3/i }))

    expect(screen.getByRole('button', { name: /downloading/i })).toBeDisabled()

    resolveDownload()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /download mp3/i })).not.toBeDisabled()
    })
  })

  it('re-enables button after download error', async () => {
    const mockDownload = jest.mocked(downloadLib.downloadAudioFile)
    mockDownload.mockRejectedValue(new Error('Network error'))

    const user = userEvent.setup()
    render(
      <DownloadButton
        audioUrl="https://example.com/audio.mp3"
        episodeTitle="My Episode"
      />
    )

    await user.click(screen.getByRole('button', { name: /download mp3/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /download mp3/i })).not.toBeDisabled()
    })
  })
})
