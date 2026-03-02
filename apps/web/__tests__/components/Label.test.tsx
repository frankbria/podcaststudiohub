import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { Label } from '@/components/ui/label'

describe('Label Component', () => {
  it('renders with children text', () => {
    render(<Label>Email</Label>)
    expect(screen.getByText('Email')).toBeInTheDocument()
  })

  it('renders as a label element', () => {
    render(<Label htmlFor="email-input">Email</Label>)
    const label = screen.getByText('Email')
    expect(label.tagName).toBe('LABEL')
  })

  it('associates with an input via htmlFor', () => {
    render(
      <>
        <Label htmlFor="email-input">Email</Label>
        <input id="email-input" />
      </>
    )
    const label = screen.getByText('Email')
    expect(label).toHaveAttribute('for', 'email-input')
  })

  it('applies a custom className', () => {
    render(<Label className="my-label">Custom</Label>)
    expect(screen.getByText('Custom')).toHaveClass('my-label')
  })

  it('forwards ref', () => {
    const ref = React.createRef<HTMLLabelElement>()
    render(<Label ref={ref}>Ref Test</Label>)
    expect(ref.current).not.toBeNull()
    expect(ref.current?.tagName).toBe('LABEL')
  })
})
