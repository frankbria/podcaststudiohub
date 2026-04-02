import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { EpisodeListSkeleton } from '@/components/skeletons/EpisodeListSkeleton'

describe('EpisodeListSkeleton', () => {
	it('renders with loading accessible label', () => {
		render(<EpisodeListSkeleton />)
		expect(screen.getByLabelText('Loading')).toBeInTheDocument()
	})

	it('renders 4 skeleton rows', () => {
		const { container } = render(<EpisodeListSkeleton />)
		const rows = container.querySelectorAll('[aria-hidden="true"]')
		expect(rows.length).toBe(4)
	})

	it('renders animated pulse elements', () => {
		const { container } = render(<EpisodeListSkeleton />)
		const animatedElements = container.querySelectorAll('.animate-pulse')
		expect(animatedElements.length).toBeGreaterThan(0)
	})
})
