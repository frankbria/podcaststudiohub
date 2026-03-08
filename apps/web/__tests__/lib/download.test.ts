import { sanitizeFilename, downloadAudioFile } from "@/lib/download"

describe("sanitizeFilename", () => {
  it("converts spaces to underscores", () => {
    expect(sanitizeFilename("My Podcast Episode")).toBe("my_podcast_episode")
  })

  it("removes invalid filename characters", () => {
    // / : ? are replaced; ( ) are preserved; spaces collapsed to single underscore
    expect(sanitizeFilename('AI/ML: The Future? (2025)')).toBe("ai_ml__the_future__(2025)")
  })

  it("converts to lowercase", () => {
    expect(sanitizeFilename("UPPER CASE TITLE")).toBe("upper_case_title")
  })

  it("limits length to 200 characters", () => {
    const longTitle = "a".repeat(300)
    expect(sanitizeFilename(longTitle)).toHaveLength(200)
  })

  it("replaces < > : \" / \\ | ? * characters", () => {
    const title = '<>:"/\\|?*test'
    const result = sanitizeFilename(title)
    expect(result).not.toMatch(/[<>:"/\\|?*]/)
    expect(result).toContain("test")
  })

  it("handles empty string", () => {
    expect(sanitizeFilename("")).toBe("")
  })

  it("replaces multiple consecutive spaces with single underscore", () => {
    // \s+ is greedy — multiple spaces collapse into one underscore
    expect(sanitizeFilename("hello   world")).toBe("hello_world")
  })

  it("handles title with episode number", () => {
    expect(sanitizeFilename("Episode 42 - AI in 2025")).toBe("episode_42_-_ai_in_2025")
  })
})

describe("downloadAudioFile", () => {
  const mockCreateObjectURL = jest.fn(() => "blob:mock-url")
  const mockRevokeObjectURL = jest.fn()
  const mockAppendChild = jest.fn()
  const mockRemoveChild = jest.fn()
  const mockClick = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()

    Object.defineProperty(window, "URL", {
      value: {
        createObjectURL: mockCreateObjectURL,
        revokeObjectURL: mockRevokeObjectURL,
      },
      writable: true,
    })

    const mockLink = {
      href: "",
      download: "",
      click: mockClick,
    } as unknown as HTMLAnchorElement

    jest.spyOn(document, "createElement").mockReturnValue(mockLink)
    jest.spyOn(document.body, "appendChild").mockImplementation(mockAppendChild)
    jest.spyOn(document.body, "removeChild").mockImplementation(mockRemoveChild)
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it("fetches the audio URL and triggers download", async () => {
    const mockBlob = new Blob(["audio-data"], { type: "audio/mpeg" })
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      blob: jest.fn().mockResolvedValue(mockBlob),
    } as unknown as Response)

    await downloadAudioFile("https://example.com/audio.mp3", "my_episode.mp3")

    expect(global.fetch).toHaveBeenCalledWith("https://example.com/audio.mp3")
    expect(mockCreateObjectURL).toHaveBeenCalledWith(mockBlob)
    expect(mockClick).toHaveBeenCalled()
    expect(mockRevokeObjectURL).toHaveBeenCalledWith("blob:mock-url")
  })

  it("sets the download filename on the link", async () => {
    const mockBlob = new Blob(["audio-data"], { type: "audio/mpeg" })
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      blob: jest.fn().mockResolvedValue(mockBlob),
    } as unknown as Response)

    const mockLink = { href: "", download: "", click: mockClick } as unknown as HTMLAnchorElement
    jest.spyOn(document, "createElement").mockReturnValue(mockLink)

    await downloadAudioFile("https://example.com/audio.mp3", "my_episode.mp3")

    expect(mockLink.download).toBe("my_episode.mp3")
    expect(mockLink.href).toBe("blob:mock-url")
  })

  it("throws when fetch returns a non-ok response", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
    } as unknown as Response)

    await expect(
      downloadAudioFile("https://example.com/missing.mp3", "missing.mp3")
    ).rejects.toThrow("Failed to fetch audio: 404 Not Found")
  })

  it("revokes the object URL even if link click throws", async () => {
    const mockBlob = new Blob(["audio-data"], { type: "audio/mpeg" })
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      blob: jest.fn().mockResolvedValue(mockBlob),
    } as unknown as Response)

    const throwingLink = {
      href: "",
      download: "",
      click: jest.fn(() => { throw new Error("click failed") }),
    } as unknown as HTMLAnchorElement
    jest.spyOn(document, "createElement").mockReturnValue(throwingLink)

    await expect(
      downloadAudioFile("https://example.com/audio.mp3", "episode.mp3")
    ).rejects.toThrow("click failed")

    expect(mockRevokeObjectURL).toHaveBeenCalledWith("blob:mock-url")
  })
})
