import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { EditProjectDialog } from '@/components/dialogs/EditProjectDialog'

const mockProject = {
  id: 'project-1',
  title: 'My Podcast',
  description: 'A great podcast',
}

describe('EditProjectDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: jest.fn(),
    project: mockProject,
    onUpdate: jest.fn().mockResolvedValue(undefined),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders with pre-populated project values', () => {
    render(<EditProjectDialog {...defaultProps} />)
    expect(screen.getByDisplayValue('My Podcast')).toBeInTheDocument()
    expect(screen.getByDisplayValue('A great podcast')).toBeInTheDocument()
  })

  it('renders Edit Project title', () => {
    render(<EditProjectDialog {...defaultProps} />)
    expect(screen.getByText('Edit Project')).toBeInTheDocument()
  })

  it('shows validation error when title is cleared', async () => {
    const user = userEvent.setup()
    render(<EditProjectDialog {...defaultProps} />)
    const titleInput = screen.getByDisplayValue('My Podcast')
    await user.clear(titleInput)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('calls onUpdate with updated values on submit', async () => {
    const user = userEvent.setup()
    render(<EditProjectDialog {...defaultProps} />)
    const titleInput = screen.getByDisplayValue('My Podcast')
    await user.clear(titleInput)
    await user.type(titleInput, 'Updated Title')
    await user.click(screen.getByRole('button', { name: /^update$/i }))
    await waitFor(() => {
      expect(defaultProps.onUpdate).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Updated Title' })
      )
    })
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<EditProjectDialog {...defaultProps} />)
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })

  it('does not render content when closed', () => {
    render(<EditProjectDialog {...defaultProps} open={false} />)
    expect(screen.queryByText('Edit Project')).not.toBeInTheDocument()
  })
})
