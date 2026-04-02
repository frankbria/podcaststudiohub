import { sanitizeFilename, downloadAudioFile } from '@/lib/download'

describe('sanitizeFilename', () => {
  it('converts spaces to underscores', () => {
    expect(sanitizeFilename('My Podcast Episode')).toBe('my_podcast_episode.mp3')
  })

  it('removes invalid filename characters', () => {
    // / : ? are invalid; ( ) are not
    expect(sanitizeFilename('AI/ML: The Future? (2025)')).toBe('ai_ml_the_future_(2025).mp3')
  })

  it('removes < > : " / \\ | ? *', () => {
    const result = sanitizeFilename('Test<>:"/\\|?*File')
    expect(result).not.toMatch(/[<>:"/\\|?*]/)
    expect(result).toMatch(/\.mp3$/)
  })

  it('converts to lowercase', () => {
    expect(sanitizeFilename('UPPERCASE TITLE')).toBe('uppercase_title.mp3')
  })

  it('limits filename to 255 chars including extension', () => {
    const longTitle = 'a'.repeat(300)
    const result = sanitizeFilename(longTitle)
    expect(result.length).toBeLessThanOrEqual(255)
    expect(result).toMatch(/\.mp3$/)
  })

  it('collapses multiple spaces', () => {
    expect(sanitizeFilename('word   word')).toBe('word_word.mp3')
  })

  it('handles title with only special characters', () => {
    const result = sanitizeFilename('???')
    expect(result).toMatch(/\.mp3$/)
  })
})

describe('downloadAudioFile', () => {
  let originalCreateObjectURL: typeof URL.createObjectURL
  let originalRevokeObjectURL: typeof URL.revokeObjectURL

  beforeEach(() => {
    originalCreateObjectURL = window.URL.createObjectURL
    originalRevokeObjectURL = window.URL.revokeObjectURL
    window.URL.createObjectURL = jest.fn(() => 'blob:mock-url')
    window.URL.revokeObjectURL = jest.fn()

    // Mock document.body.appendChild/removeChild
    jest.spyOn(document.body, 'appendChild').mockImplementation((node) => node)
    jest.spyOn(document.body, 'removeChild').mockImplementation((node) => node)
  })

  afterEach(() => {
    window.URL.createObjectURL = originalCreateObjectURL
    window.URL.revokeObjectURL = originalRevokeObjectURL
    jest.restoreAllMocks()
  })

  it('fetches the URL and creates a download link', async () => {
    const mockBlob = new Blob(['audio data'], { type: 'audio/mpeg' })
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      blob: jest.fn().mockResolvedValue(mockBlob),
    } as unknown as Response)

    const clickMock = jest.fn()
    const createElementSpy = jest.spyOn(document, 'createElement').mockReturnValue({
      href: '',
      download: '',
      click: clickMock,
    } as unknown as HTMLAnchorElement)

    await downloadAudioFile('https://example.com/audio.mp3', 'test_episode.mp3')

    expect(global.fetch).toHaveBeenCalledWith('https://example.com/audio.mp3')
    expect(window.URL.createObjectURL).toHaveBeenCalledWith(mockBlob)
    expect(clickMock).toHaveBeenCalled()
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')

    createElementSpy.mockRestore()
  })

  it('throws an error if fetch response is not ok', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
    } as unknown as Response)

    await expect(
      downloadAudioFile('https://example.com/missing.mp3', 'test.mp3')
    ).rejects.toThrow('Failed to fetch audio: 404 Not Found')
  })
})
