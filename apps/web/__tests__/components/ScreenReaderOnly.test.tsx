import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { ScreenReaderOnly } from '@/components/ScreenReaderOnly'

describe('ScreenReaderOnly', () => {
  it('renders children text', () => {
    render(<ScreenReaderOnly>Edit project</ScreenReaderOnly>)
    expect(screen.getByText('Edit project')).toBeInTheDocument()
  })

  it('applies sr-only class for visual hiding', () => {
    render(<ScreenReaderOnly>Hidden label</ScreenReaderOnly>)
    const span = screen.getByText('Hidden label')
    expect(span).toHaveClass('sr-only')
  })

  it('renders as a span element', () => {
    render(<ScreenReaderOnly>Accessible text</ScreenReaderOnly>)
    const span = screen.getByText('Accessible text')
    expect(span.tagName).toBe('SPAN')
  })
})
