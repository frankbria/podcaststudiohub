import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { DashboardSkeleton } from '@/components/skeletons/DashboardSkeleton'

describe('DashboardSkeleton', () => {
	it('renders with accessible loading label', () => {
		render(<DashboardSkeleton />)
		expect(screen.getByRole('status', { name: /loading projects/i })).toBeInTheDocument()
	})

	it('renders 6 card skeletons', () => {
		const { container } = render(<DashboardSkeleton />)
		// Each CardSkeleton has aria-hidden="true" on its root div
		const skeletonCards = container.querySelectorAll('[aria-hidden="true"]')
		// 6 cards + 2 header elements
		expect(skeletonCards.length).toBeGreaterThanOrEqual(6)
	})

	it('renders pulse animation elements', () => {
		const { container } = render(<DashboardSkeleton />)
		const pulseElements = container.querySelectorAll('.animate-pulse')
		expect(pulseElements.length).toBeGreaterThan(0)
	})
})
