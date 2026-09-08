import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RouteError from '@/app/error'

describe('RouteError boundary', () => {
  let consoleError: jest.SpyInstance

  beforeEach(() => {
    consoleError = jest.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    consoleError.mockRestore()
  })

  it('shows the error message in an alert and logs it', () => {
    const error = new Error('Objects are not valid as a React child')

    render(<RouteError error={error} reset={jest.fn()} />)

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Objects are not valid as a React child'
    )
    expect(consoleError).toHaveBeenCalledWith('Route render error:', error)
  })

  it('calls reset when the retry button is clicked', async () => {
    const reset = jest.fn()

    render(<RouteError error={new Error('boom')} reset={reset} />)
    await userEvent.click(screen.getByRole('button', { name: /try again/i }))

    expect(reset).toHaveBeenCalledTimes(1)
  })

  it('renders the digest reference when present', () => {
    const error = Object.assign(new Error('boom'), { digest: 'abc123' })

    render(<RouteError error={error} reset={jest.fn()} />)

    expect(screen.getByText('abc123')).toBeInTheDocument()
  })

  it('falls back to a placeholder when the error has no message', () => {
    render(<RouteError error={new Error('')} reset={jest.fn()} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Unknown error')
  })
})
