import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import * as React from "react"
import { DownloadButton } from "@/components/DownloadButton"
import * as downloadLib from "@/lib/download"

jest.mock("@/lib/download", () => ({
  sanitizeFilename: jest.fn((title: string) => title.toLowerCase().replace(/\s+/g, "_")),
  downloadAudioFile: jest.fn(),
}))

describe("DownloadButton", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("renders with 'Download MP3' label", () => {
    render(
      <DownloadButton audioUrl="https://example.com/audio.mp3" episodeTitle="My Episode" />
    )
    expect(screen.getByRole("button", { name: /download mp3/i })).toBeInTheDocument()
  })

  it("is disabled when audioUrl is null", () => {
    render(<DownloadButton audioUrl={null} episodeTitle="My Episode" />)
    expect(screen.getByRole("button")).toBeDisabled()
  })

  it("is disabled when audioUrl is undefined", () => {
    render(<DownloadButton audioUrl={undefined} episodeTitle="My Episode" />)
    expect(screen.getByRole("button")).toBeDisabled()
  })

  it("is disabled when isLoading is true", () => {
    render(
      <DownloadButton audioUrl="https://example.com/audio.mp3" episodeTitle="My Episode" isLoading />
    )
    expect(screen.getByRole("button")).toBeDisabled()
  })

  it("is enabled when audioUrl is provided and not loading", () => {
    render(
      <DownloadButton audioUrl="https://example.com/audio.mp3" episodeTitle="My Episode" />
    )
    expect(screen.getByRole("button")).not.toBeDisabled()
  })

  it("calls downloadAudioFile with sanitized filename on click", async () => {
    const mockDownload = downloadLib.downloadAudioFile as jest.Mock
    mockDownload.mockResolvedValue(undefined)

    const user = userEvent.setup()
    render(
      <DownloadButton audioUrl="https://example.com/audio.mp3" episodeTitle="My Episode Title" />
    )

    await user.click(screen.getByRole("button"))

    await waitFor(() => {
      expect(mockDownload).toHaveBeenCalledWith(
        "https://example.com/audio.mp3",
        "my_episode_title.mp3"
      )
    })
  })

  it("shows 'Downloading...' label while downloading", async () => {
    let resolveDownload!: () => void
    const mockDownload = downloadLib.downloadAudioFile as jest.Mock
    mockDownload.mockImplementation(
      () => new Promise<void>((resolve) => { resolveDownload = resolve })
    )

    const user = userEvent.setup()
    render(
      <DownloadButton audioUrl="https://example.com/audio.mp3" episodeTitle="My Episode" />
    )

    await user.click(screen.getByRole("button"))

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /downloading\.\.\./i })).toBeInTheDocument()
      expect(screen.getByRole("button")).toBeDisabled()
    })

    resolveDownload()

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /download mp3/i })).toBeInTheDocument()
      expect(screen.getByRole("button")).not.toBeDisabled()
    })
  })

  it("re-enables button if download fails", async () => {
    const mockDownload = downloadLib.downloadAudioFile as jest.Mock
    mockDownload.mockRejectedValue(new Error("Network error"))

    const consoleSpy = jest.spyOn(console, "error").mockImplementation(() => {})
    const user = userEvent.setup()

    render(
      <DownloadButton audioUrl="https://example.com/audio.mp3" episodeTitle="My Episode" />
    )

    await user.click(screen.getByRole("button"))

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /download mp3/i })).toBeInTheDocument()
      expect(screen.getByRole("button")).not.toBeDisabled()
    })

    consoleSpy.mockRestore()
  })

  it("logs error to console when download fails", async () => {
    const error = new Error("Download failed")
    const mockDownload = downloadLib.downloadAudioFile as jest.Mock
    mockDownload.mockRejectedValue(error)

    const consoleSpy = jest.spyOn(console, "error").mockImplementation(() => {})
    const user = userEvent.setup()

    render(
      <DownloadButton audioUrl="https://example.com/audio.mp3" episodeTitle="My Episode" />
    )

    await user.click(screen.getByRole("button"))

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalledWith("Download failed:", error)
    })

    consoleSpy.mockRestore()
  })

  it("does not call downloadAudioFile when audioUrl is null", async () => {
    const mockDownload = downloadLib.downloadAudioFile as jest.Mock
    const user = userEvent.setup()

    render(<DownloadButton audioUrl={null} episodeTitle="My Episode" />)

    // Button is disabled, click should not trigger handler
    const button = screen.getByRole("button")
    expect(button).toBeDisabled()
    expect(mockDownload).not.toHaveBeenCalled()
  })
})
