import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderToStaticMarkup } from 'react-dom/server'
import GlobalError from '@/app/global-error'
import { reportClientError } from '@/lib/report-client-error'

jest.mock('@/lib/report-client-error', () => ({
  reportClientError: jest.fn(),
}))

const reportMock = reportClientError as jest.Mock

/**
 * global-error.tsx is the boundary of last resort: `app/error.tsx` only catches
 * throws inside a route, so a throw in `app/layout.tsx` itself bypasses it and
 * the user gets the browser's own "This page couldn't load" — the exact failure
 * #481 was about (issue #485, item 2).
 *
 * It replaces the root layout, so it must render its own <html>/<body>. jsdom
 * mounts that inside a <div>, which React reports as invalid nesting; the
 * console spy below absorbs that so a real regression is still visible.
 */
describe('GlobalError boundary', () => {
  let consoleError: jest.SpyInstance

  beforeEach(() => {
    consoleError = jest.spyOn(console, 'error').mockImplementation(() => {})
    reportMock.mockReset()
  })

  afterEach(() => {
    consoleError.mockRestore()
  })

  it('renders its own html and body, since the root layout is gone', () => {
    // Asserted through a server render, not `render()`: React 19 hoists <html>
    // and <body> out of jsdom's container, so a DOM query there would pass
    // vacuously whether or not the tags are in the component at all.
    const markup = renderToStaticMarkup(
      <GlobalError error={new Error('layout blew up')} reset={jest.fn()} />
    )

    expect(markup).toMatch(/^<html lang="en"[^>]*>(<head><\/head>)?<body[^>]*>/)
    expect(markup).toContain('Something went wrong')
  })

  it('shows the error message in an alert', () => {
    render(<GlobalError error={new Error('layout blew up')} reset={jest.fn()} />)

    expect(screen.getByRole('alert')).toHaveTextContent('layout blew up')
  })

  it('reports the error to the relay so a layout crash is not invisible', () => {
    const error = Object.assign(new Error('layout blew up'), { digest: 'deadbeef' })

    render(<GlobalError error={error} reset={jest.fn()} />)

    expect(reportMock).toHaveBeenCalledWith(error, 'global-error')
  })

  it('renders the digest reference when present', () => {
    render(
      <GlobalError
        error={Object.assign(new Error('boom'), { digest: 'deadbeef' })}
        reset={jest.fn()}
      />
    )

    expect(screen.getByText('deadbeef')).toBeInTheDocument()
  })

  it('calls reset when the retry button is clicked', async () => {
    const reset = jest.fn()

    render(<GlobalError error={new Error('boom')} reset={reset} />)
    await userEvent.click(screen.getByRole('button', { name: /try again/i }))

    expect(reset).toHaveBeenCalledTimes(1)
  })

  it('hides the raw error message in production and keeps the digest', () => {
    jest.replaceProperty(process.env, 'NODE_ENV', 'production')

    render(
      <GlobalError
        error={Object.assign(new Error('Minified React error #31'), { digest: 'xyz789' })}
        reset={jest.fn()}
      />
    )

    expect(screen.getByRole('alert')).toHaveTextContent('The page could not be displayed.')
    expect(screen.queryByText(/Minified React error/)).not.toBeInTheDocument()
    expect(screen.getByText('xyz789')).toBeInTheDocument()
  })
})
