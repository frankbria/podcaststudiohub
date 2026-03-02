import { render, screen } from '@testing-library/react'
import * as React from 'react'
// @radix-ui/react-progress is mapped to a stub via jest.config.js moduleNameMapper
import { Progress } from '@/components/ui/progress'

describe('Progress Component', () => {
  it('renders without errors', () => {
    const { container } = render(<Progress value={50} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it('renders with role progressbar', () => {
    render(<Progress value={50} aria-label="loading" />)
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('applies a custom className', () => {
    const { container } = render(<Progress className="my-progress" value={25} />)
    expect(container.firstChild).toHaveClass('my-progress')
  })

  it('handles value=0 (uses 0, not undefined)', () => {
    render(<Progress value={0} />)
    const indicator = screen.getByTestId('progress-indicator')
    expect(indicator).toHaveStyle({ transform: 'translateX(-100%)' })
  })

  it('handles value=100 (fully filled)', () => {
    render(<Progress value={100} />)
    const indicator = screen.getByTestId('progress-indicator')
    expect(indicator).toHaveStyle({ transform: 'translateX(-0%)' })
  })

  it('handles undefined value (falls back to 0)', () => {
    render(<Progress />)
    const indicator = screen.getByTestId('progress-indicator')
    expect(indicator).toHaveStyle({ transform: 'translateX(-100%)' })
  })

  it('forwards ref', () => {
    const ref = React.createRef<HTMLDivElement>()
    render(<Progress ref={ref} value={50} />)
    expect(ref.current).not.toBeNull()
  })
})
