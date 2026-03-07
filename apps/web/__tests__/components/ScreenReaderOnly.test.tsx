import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { ScreenReaderOnly } from '@/components/ScreenReaderOnly'

describe('ScreenReaderOnly', () => {
  it('renders children text', () => {
    render(<ScreenReaderOnly>Edit project</ScreenReaderOnly>)
    expect(screen.getByText('Edit project')).toBeInTheDocument()
  })

  it('has sr-only class', () => {
    render(<ScreenReaderOnly>Hidden label</ScreenReaderOnly>)
    const span = screen.getByText('Hidden label')
    expect(span).toHaveClass('sr-only')
  })

  it('renders as a span element', () => {
    render(<ScreenReaderOnly>Label text</ScreenReaderOnly>)
    const el = screen.getByText('Label text')
    expect(el.tagName.toLowerCase()).toBe('span')
  })
})
