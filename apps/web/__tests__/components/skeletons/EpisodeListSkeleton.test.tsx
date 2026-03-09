import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { EpisodeListSkeleton } from '@/components/skeletons/EpisodeListSkeleton'

describe('EpisodeListSkeleton', () => {
  it('renders the episode list skeleton container', () => {
    render(<EpisodeListSkeleton />)
    expect(screen.getByTestId('episode-list-skeleton')).toBeInTheDocument()
  })

  it('announces loading state to screen readers', () => {
    render(<EpisodeListSkeleton />)
    expect(screen.getByLabelText('Loading')).toBeInTheDocument()
  })

  it('renders 4 episode skeleton rows', () => {
    const { container } = render(<EpisodeListSkeleton />)
    const rows = container.querySelectorAll('[aria-hidden="true"]')
    expect(rows.length).toBe(4)
  })

  it('applies animate-pulse to skeleton elements', () => {
    const { container } = render(<EpisodeListSkeleton />)
    const pulseElements = container.querySelectorAll('.animate-pulse')
    expect(pulseElements.length).toBeGreaterThan(0)
  })
})
