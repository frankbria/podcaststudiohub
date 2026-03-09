import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { CardSkeleton } from '@/components/skeletons/CardSkeleton'

describe('CardSkeleton', () => {
  it('renders the skeleton container', () => {
    render(<CardSkeleton />)
    expect(screen.getByTestId('card-skeleton')).toBeInTheDocument()
  })

  it('is hidden from screen readers', () => {
    render(<CardSkeleton />)
    expect(screen.getByTestId('card-skeleton')).toHaveAttribute('aria-hidden', 'true')
  })

  it('applies animate-pulse to skeleton elements', () => {
    const { container } = render(<CardSkeleton />)
    const pulseElements = container.querySelectorAll('.animate-pulse')
    expect(pulseElements.length).toBeGreaterThan(0)
  })
})
