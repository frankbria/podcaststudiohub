import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { DashboardSkeleton } from '@/components/skeletons/DashboardSkeleton'

describe('DashboardSkeleton', () => {
	it('renders with loading accessible label', () => {
		render(<DashboardSkeleton />)
		expect(screen.getByLabelText('Loading')).toBeInTheDocument()
	})

	it('renders 6 card skeletons', () => {
		const { container } = render(<DashboardSkeleton />)
		// Each CardSkeleton has aria-hidden="true" on root div
		const cardSkeletons = container.querySelectorAll('[aria-hidden="true"]')
		expect(cardSkeletons.length).toBe(6)
	})

	it('renders animated pulse elements', () => {
		const { container } = render(<DashboardSkeleton />)
		const animatedElements = container.querySelectorAll('.animate-pulse')
		expect(animatedElements.length).toBeGreaterThan(0)
	})
})
