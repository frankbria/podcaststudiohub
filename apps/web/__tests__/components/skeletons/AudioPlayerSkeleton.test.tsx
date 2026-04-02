import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { AudioPlayerSkeleton } from '@/components/skeletons/AudioPlayerSkeleton'

describe('AudioPlayerSkeleton', () => {
	it('renders with loading accessible label', () => {
		render(<AudioPlayerSkeleton />)
		expect(screen.getByLabelText('Loading')).toBeInTheDocument()
	})

	it('renders animated pulse elements', () => {
		const { container } = render(<AudioPlayerSkeleton />)
		const animatedElements = container.querySelectorAll('.animate-pulse')
		expect(animatedElements.length).toBeGreaterThan(0)
	})
})
