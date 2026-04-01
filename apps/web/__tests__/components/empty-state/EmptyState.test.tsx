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
				title="No projects"
				description="Create one"
				action={{ label: 'Create Project', onClick: handleClick }}
			/>
		)
		expect(screen.getByRole('button', { name: 'Create Project' })).toBeInTheDocument()
	})

	it('calls action onClick when button is clicked', () => {
		const handleClick = jest.fn()
		render(
			<EmptyState
				title="No projects"
				description="Create one"
				action={{ label: 'Create Project', onClick: handleClick }}
			/>
		)
		fireEvent.click(screen.getByRole('button', { name: 'Create Project' }))
		expect(handleClick).toHaveBeenCalledTimes(1)
	})

	it('does not render a button when no action prop', () => {
		render(
			<EmptyState title="No projects" description="Nothing here" />
		)
		expect(screen.queryByRole('button')).not.toBeInTheDocument()
	})

	it('renders icon when provided', () => {
		render(
			<EmptyState
				title="No projects"
				description="Nothing here"
				icon={<span data-testid="test-icon">icon</span>}
			/>
		)
		expect(screen.getByTestId('test-icon')).toBeInTheDocument()
	})

	it('does not render icon container when no icon is provided', () => {
		const { container } = render(
			<EmptyState title="No projects" description="Nothing here" />
		)
		// No icon wrapper div should be present
		const iconWrappers = container.querySelectorAll('.mb-4')
		expect(iconWrappers.length).toBe(0)
	})
})
