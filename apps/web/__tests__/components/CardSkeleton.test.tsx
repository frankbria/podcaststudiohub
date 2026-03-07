import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { CardSkeleton } from '@/components/skeletons/CardSkeleton'

describe('CardSkeleton', () => {
	it('renders without crashing', () => {
		const { container } = render(<CardSkeleton />)
		expect(container.firstChild).toBeInTheDocument()
	})

	it('has aria-hidden for screen readers', () => {
		const { container } = render(<CardSkeleton />)
		expect(container.firstChild).toHaveAttribute('aria-hidden', 'true')
	})

	it('renders pulse animation elements', () => {
		const { container } = render(<CardSkeleton />)
		const pulseElements = container.querySelectorAll('.animate-pulse')
		expect(pulseElements.length).toBeGreaterThan(0)
	})
})
