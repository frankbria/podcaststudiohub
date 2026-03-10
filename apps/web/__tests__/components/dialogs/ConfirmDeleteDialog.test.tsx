import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { ConfirmDeleteDialog } from '@/components/dialogs/ConfirmDeleteDialog'

describe('ConfirmDeleteDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: jest.fn(),
    title: 'Delete Project?',
    description: 'This action cannot be undone.',
    entityName: 'My Podcast',
    onConfirm: jest.fn().mockResolvedValue(undefined),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders dialog with title, description, and entity name when open', () => {
    render(<ConfirmDeleteDialog {...defaultProps} />)
    expect(screen.getByText('Delete Project?')).toBeInTheDocument()
    expect(screen.getByText('This action cannot be undone.')).toBeInTheDocument()
    expect(screen.getByText(/My Podcast/)).toBeInTheDocument()
  })

  it('does not render when open is false', () => {
    render(<ConfirmDeleteDialog {...defaultProps} open={false} />)
    expect(screen.queryByText('Delete Project?')).not.toBeInTheDocument()
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
    expect(defaultProps.onConfirm).toHaveBeenCalledTimes(1)
  })

  it('shows loading state while deleting', () => {
    render(<ConfirmDeleteDialog {...defaultProps} isLoading={true} />)
    expect(screen.getByRole('button', { name: /deleting/i })).toBeDisabled()
  })

  it('disables both buttons while loading', () => {
    render(<ConfirmDeleteDialog {...defaultProps} isLoading={true} />)
    const buttons = screen.getAllByRole('button')
    buttons.forEach((btn) => {
      if (btn.textContent !== 'Close') {
        expect(btn).toBeDisabled()
      }
    })
  })

  it('shows error message when deletion fails', async () => {
    const user = userEvent.setup()
    const onConfirm = jest.fn().mockRejectedValue(new Error('Network error'))
    render(<ConfirmDeleteDialog {...defaultProps} onConfirm={onConfirm} />)
    await user.click(screen.getByRole('button', { name: /^delete$/i }))
    await waitFor(() => {
      expect(screen.getByText(/failed to delete/i)).toBeInTheDocument()
    })
  })

  it('closes dialog via Escape key', async () => {
    const user = userEvent.setup()
    render(<ConfirmDeleteDialog {...defaultProps} />)
    await user.keyboard('{Escape}')
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })
})
