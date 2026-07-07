/**
 * Layers a URL/method-matched mock response on top of an existing `fetch`
 * mock, falling back to the base implementation for every other request.
 * Lets a single `mock*FetchRouter()` cover a page's happy-path mount fetches
 * while an individual test swaps in one endpoint's success/failure/network-
 * error response.
 *
 * Deliberately placed outside `__tests__/` (jest's testMatch would otherwise
 * pick this file up as a test suite with zero tests) and outside `src/`
 * (jest.config.js's collectCoverageFrom would otherwise count it against
 * frontend coverage).
 */
export function withOverride(
  base: jest.Mock,
  matcher: (url: string, init?: RequestInit) => boolean,
  handler: () => Promise<unknown>
): jest.Mock {
  const baseImpl = base.getMockImplementation()!
  base.mockImplementation((url: string, init?: RequestInit) => {
    if (matcher(url, init)) {
      return handler()
    }
    return baseImpl(url, init)
  })
  return base
}
