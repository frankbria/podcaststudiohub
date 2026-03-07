import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { EpisodeListSkeleton } from '@/components/skeletons/EpisodeListSkeleton'

describe('EpisodeListSkeleton', () => {
	it('renders with accessible loading label', () => {
		render(<EpisodeListSkeleton />)
		expect(screen.getByRole('status', { name: /loading episodes/i })).toBeInTheDocument()
	})

	it('renders 4 episode skeleton rows', () => {
		const { container } = render(<EpisodeListSkeleton />)
		const episodeRows = container.querySelectorAll('[aria-hidden="true"]')
		expect(episodeRows.length).toBe(4)
	})

	it('renders pulse animation elements', () => {
		const { container } = render(<EpisodeListSkeleton />)
		const pulseElements = container.querySelectorAll('.animate-pulse')
		expect(pulseElements.length).toBeGreaterThan(0)
	})
})
