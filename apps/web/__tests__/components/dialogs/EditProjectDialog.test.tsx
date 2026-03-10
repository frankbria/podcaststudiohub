import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { EditProjectDialog } from '@/components/dialogs/EditProjectDialog'

const mockProject = {
  id: 'project-1',
  title: 'My Podcast',
  description: 'A great podcast',
  episode_count: 3,
  created_at: '2024-01-01T00:00:00Z',
}

describe('EditProjectDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: jest.fn(),
    project: mockProject,
    onUpdate: jest.fn(),
    onSave: jest.fn().mockResolvedValue(undefined),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders dialog when open is true', () => {
    render(<EditProjectDialog {...defaultProps} />)
    expect(screen.getByText(/edit project/i)).toBeInTheDocument()
  })

  it('does not render when open is false', () => {
    render(<EditProjectDialog {...defaultProps} open={false} />)
    expect(screen.queryByText(/edit project/i)).not.toBeInTheDocument()
  })

  it('pre-populates form fields with project data', () => {
    render(<EditProjectDialog {...defaultProps} />)
    const titleInput = screen.getByDisplayValue('My Podcast')
    expect(titleInput).toBeInTheDocument()
    const descriptionInput = screen.getByDisplayValue('A great podcast')
    expect(descriptionInput).toBeInTheDocument()
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const onOpenChange = jest.fn()
    render(<EditProjectDialog {...defaultProps} onOpenChange={onOpenChange} />)
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('calls onSave with updated values when form is submitted', async () => {
    const user = userEvent.setup()
    const onSave = jest.fn().mockResolvedValue(undefined)
    render(<EditProjectDialog {...defaultProps} onSave={onSave} />)

    const titleInput = screen.getByDisplayValue('My Podcast')
    await user.clear(titleInput)
    await user.type(titleInput, 'Updated Podcast')

    await user.click(screen.getByRole('button', { name: /update/i }))
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Updated Podcast' })
    )
  })

  it('disables submit button when title is empty', async () => {
    const user = userEvent.setup()
    render(<EditProjectDialog {...defaultProps} />)
    const titleInput = screen.getByDisplayValue('My Podcast')
    await user.clear(titleInput)
    const submitButton = screen.getByRole('button', { name: /update/i })
    expect(submitButton).toBeDisabled()
  })

  it('shows loading state when isLoading is true', () => {
    render(<EditProjectDialog {...defaultProps} isLoading={true} />)
    const updateButton = screen.getByRole('button', { name: /updating/i })
    expect(updateButton).toBeDisabled()
  })
})
