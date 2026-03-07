import { render, screen, fireEvent } from '@testing-library/react'
import * as React from 'react'
import { EmptyState } from '@/components/empty-state/EmptyState'

describe('EmptyState', () => {
	it('renders title and description', () => {
		render(
			<EmptyState
				title="No projects yet"
				description="Create your first podcast project to get started"
			/>
		)
		expect(screen.getByText('No projects yet')).toBeInTheDocument()
		expect(screen.getByText('Create your first podcast project to get started')).toBeInTheDocument()
	})

	it('renders action button when action prop is provided', () => {
		const handleClick = jest.fn()
		render(
			<EmptyState
				title="No projects yet"
				description="Create your first project"
				action={{ label: 'Create Project', onClick: handleClick }}
			/>
		)
		const button = screen.getByRole('button', { name: /create project/i })
		expect(button).toBeInTheDocument()
	})

	it('calls action onClick when button is clicked', () => {
		const handleClick = jest.fn()
		render(
			<EmptyState
				title="No projects yet"
				description="Create your first project"
				action={{ label: 'Create Project', onClick: handleClick }}
			/>
		)
		fireEvent.click(screen.getByRole('button', { name: /create project/i }))
		expect(handleClick).toHaveBeenCalledTimes(1)
	})

	it('does not render button when action prop is absent', () => {
		render(
			<EmptyState
				title="No projects yet"
				description="Create your first project"
			/>
		)
		expect(screen.queryByRole('button')).not.toBeInTheDocument()
	})

	it('renders icon when provided', () => {
		render(
			<EmptyState
				icon={<span data-testid="test-icon">icon</span>}
				title="No projects yet"
				description="Create your first project"
			/>
		)
		expect(screen.getByTestId('test-icon')).toBeInTheDocument()
	})

	it('does not render icon container when icon is absent', () => {
		const { container } = render(
			<EmptyState
				title="No projects yet"
				description="Create your first project"
			/>
		)
		// No aria-hidden icon container
		expect(container.querySelector('[aria-hidden="true"]')).not.toBeInTheDocument()
	})
})
