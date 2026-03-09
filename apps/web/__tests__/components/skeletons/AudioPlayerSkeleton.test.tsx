import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { AudioPlayerSkeleton } from '@/components/skeletons/AudioPlayerSkeleton'

describe('AudioPlayerSkeleton', () => {
  it('renders the audio player skeleton container', () => {
    render(<AudioPlayerSkeleton />)
    expect(screen.getByTestId('audio-player-skeleton')).toBeInTheDocument()
  })

  it('announces loading state to screen readers', () => {
    render(<AudioPlayerSkeleton />)
    expect(screen.getByLabelText('Loading audio player')).toBeInTheDocument()
  })

  it('applies animate-pulse to skeleton elements', () => {
    const { container } = render(<AudioPlayerSkeleton />)
    const pulseElements = container.querySelectorAll('.animate-pulse')
    expect(pulseElements.length).toBeGreaterThan(0)
  })
})
