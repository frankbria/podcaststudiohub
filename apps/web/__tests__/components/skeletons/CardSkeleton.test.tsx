import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { CardSkeleton } from '@/components/skeletons/CardSkeleton'

describe('CardSkeleton', () => {
	it('renders skeleton placeholder elements', () => {
		const { container } = render(<CardSkeleton />)
		const animatedElements = container.querySelectorAll('.animate-pulse')
		expect(animatedElements.length).toBeGreaterThan(0)
	})

	it('is hidden from screen readers via aria-hidden', () => {
		const { container } = render(<CardSkeleton />)
		const root = container.firstChild as HTMLElement
		expect(root).toHaveAttribute('aria-hidden', 'true')
	})
})
