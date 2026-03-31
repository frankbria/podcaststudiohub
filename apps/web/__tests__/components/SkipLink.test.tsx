import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { SkipLink } from '@/components/SkipLink'

describe('SkipLink', () => {
  it('renders a link to #main-content', () => {
    render(<SkipLink />)
    const link = screen.getByRole('link', { name: /skip to main content/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '#main-content')
  })

  it('has sr-only class by default (visually hidden)', () => {
    render(<SkipLink />)
    const link = screen.getByRole('link', { name: /skip to main content/i })
    expect(link).toHaveClass('sr-only')
  })
})
