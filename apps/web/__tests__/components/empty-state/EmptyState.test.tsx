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

  it('renders an icon when provided', () => {
    render(
      <EmptyState
        icon={<span data-testid="test-icon">icon</span>}
        title="No projects yet"
        description="Create your first project"
      />
    )
    expect(screen.getByTestId('test-icon')).toBeInTheDocument()
  })

  it('does not render icon container when no icon provided', () => {
    render(
      <EmptyState
        title="No projects yet"
        description="Create your first project"
      />
    )
    expect(screen.queryByTestId('test-icon')).not.toBeInTheDocument()
  })

  it('renders action button when action provided', () => {
    const onClick = jest.fn()
    render(
      <EmptyState
        title="No projects yet"
        description="Create your first project"
        action={{ label: 'Create Project', onClick }}
      />
    )
    expect(screen.getByRole('button', { name: 'Create Project' })).toBeInTheDocument()
  })

  it('calls action onClick when button is clicked', () => {
    const onClick = jest.fn()
    render(
      <EmptyState
        title="No projects yet"
        description="Create your first project"
        action={{ label: 'Create Project', onClick }}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Create Project' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('does not render action button when no action provided', () => {
    render(
      <EmptyState
        title="No projects yet"
        description="Create your first project"
      />
    )
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders the empty state container', () => {
    render(
      <EmptyState
        title="No projects yet"
        description="Create your first project"
      />
    )
    expect(screen.getByTestId('empty-state')).toBeInTheDocument()
  })
})
