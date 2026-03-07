import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { AudioPlayerSkeleton } from '@/components/skeletons/AudioPlayerSkeleton'

describe('AudioPlayerSkeleton', () => {
	it('renders with accessible loading label', () => {
		render(<AudioPlayerSkeleton />)
		expect(screen.getByRole('status', { name: /loading audio player/i })).toBeInTheDocument()
	})

	it('renders pulse animation elements', () => {
		const { container } = render(<AudioPlayerSkeleton />)
		const pulseElements = container.querySelectorAll('.animate-pulse')
		expect(pulseElements.length).toBeGreaterThan(0)
	})
})
