import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { ScreenReaderOnly } from '@/components/ScreenReaderOnly'

describe('ScreenReaderOnly', () => {
  it('renders children', () => {
    render(<ScreenReaderOnly>Edit project</ScreenReaderOnly>)
    expect(screen.getByText('Edit project')).toBeInTheDocument()
  })

  it('applies sr-only class', () => {
    render(<ScreenReaderOnly>Hidden text</ScreenReaderOnly>)
    const el = screen.getByText('Hidden text')
    expect(el).toHaveClass('sr-only')
  })
})
