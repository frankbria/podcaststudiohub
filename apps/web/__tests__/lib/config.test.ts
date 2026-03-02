describe('lib/config', () => {
  const originalEnv = process.env.NEXT_PUBLIC_API_URL

  beforeEach(() => {
    // Clear module registry so each test gets a fresh import
    jest.resetModules()
    // Remove window.__ENV__ if set
    if (typeof window !== 'undefined') {
      delete (window as any).__ENV__
    }
    // Reset env var
    delete process.env.NEXT_PUBLIC_API_URL
  })

  afterEach(() => {
    if (originalEnv !== undefined) {
      process.env.NEXT_PUBLIC_API_URL = originalEnv
    } else {
      delete process.env.NEXT_PUBLIC_API_URL
    }
    if (typeof window !== 'undefined') {
      delete (window as any).__ENV__
    }
  })

  it('returns apiUrl from window.__ENV__ when set', () => {
    ;(window as any).__ENV__ = { API_URL: 'https://runtime.example.com' }
    const { getConfig } = require('@/lib/config')
    expect(getConfig().apiUrl).toBe('https://runtime.example.com')
  })

  it('returns apiUrl from NEXT_PUBLIC_API_URL when window.__ENV__ is absent', () => {
    process.env.NEXT_PUBLIC_API_URL = 'https://buildtime.example.com'
    const { getConfig } = require('@/lib/config')
    expect(getConfig().apiUrl).toBe('https://buildtime.example.com')
  })

  it('falls back to http://localhost:8000 when neither is set', () => {
    const { getConfig } = require('@/lib/config')
    expect(getConfig().apiUrl).toBe('http://localhost:8000')
  })

  it('config.apiUrl calls getConfig() each time (dynamic getter)', () => {
    const { config, getConfig } = require('@/lib/config')
    // Before setting window.__ENV__
    const first = config.apiUrl
    // Now set a runtime override
    ;(window as any).__ENV__ = { API_URL: 'https://dynamic.example.com' }
    const second = config.apiUrl
    // The getter reads window.__ENV__ dynamically
    expect(second).toBe('https://dynamic.example.com')
    expect(first).not.toBe(second)
  })
})
