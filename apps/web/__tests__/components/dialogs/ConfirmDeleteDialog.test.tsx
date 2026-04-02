import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { ConfirmDeleteDialog } from '@/components/dialogs/ConfirmDeleteDialog'

describe('ConfirmDeleteDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: jest.fn(),
    title: 'Delete Project?',
    description: 'This will permanently delete the project.',
    entityName: 'My Podcast',
    onConfirm: jest.fn().mockResolvedValue(undefined),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders the dialog with title and entity name when open', () => {
    render(<ConfirmDeleteDialog {...defaultProps} />)
    expect(screen.getByText('Delete Project?')).toBeInTheDocument()
    expect(screen.getByText(/My Podcast/)).toBeInTheDocument()
  })

  it('renders Cancel and Delete buttons', () => {
    render(<ConfirmDeleteDialog {...defaultProps} />)
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument()
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<ConfirmDeleteDialog {...defaultProps} />)
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })

  it('calls onConfirm when Delete is clicked', async () => {
    const user = userEvent.setup()
    render(<ConfirmDeleteDialog {...defaultProps} />)
    await user.click(screen.getByRole('button', { name: /^delete$/i }))
    expect(defaultProps.onConfirm).toHaveBeenCalled()
  })

  it('shows Deleting... and disables buttons when isLoading is true', () => {
    render(<ConfirmDeleteDialog {...defaultProps} isLoading={true} />)
    expect(screen.getByRole('button', { name: /deleting/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled()
  })

  it('does not render content when closed', () => {
    render(<ConfirmDeleteDialog {...defaultProps} open={false} />)
    expect(screen.queryByText('Delete Project?')).not.toBeInTheDocument()
  })
})
