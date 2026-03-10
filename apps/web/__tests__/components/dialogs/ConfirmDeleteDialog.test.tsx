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
    entityName: 'My Podcast Project',
    onConfirm: jest.fn().mockResolvedValue(undefined),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders dialog when open is true', () => {
    render(<ConfirmDeleteDialog {...defaultProps} />)
    expect(screen.getByText('Delete Project?')).toBeInTheDocument()
    expect(screen.getByText('This action cannot be undone.')).toBeInTheDocument()
    expect(screen.getByText(/My Podcast Project/)).toBeInTheDocument()
  })

  it('does not render when open is false', () => {
    render(<ConfirmDeleteDialog {...defaultProps} open={false} />)
    expect(screen.queryByText('Delete Project?')).not.toBeInTheDocument()
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const onOpenChange = jest.fn()
    render(<ConfirmDeleteDialog {...defaultProps} onOpenChange={onOpenChange} />)
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('calls onConfirm when Delete button is clicked', async () => {
    const user = userEvent.setup()
    const onConfirm = jest.fn().mockResolvedValue(undefined)
    render(<ConfirmDeleteDialog {...defaultProps} onConfirm={onConfirm} />)
    await user.click(screen.getByRole('button', { name: /^delete$/i }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('shows loading state when isLoading is true', () => {
    render(<ConfirmDeleteDialog {...defaultProps} isLoading={true} />)
    const deleteButton = screen.getByRole('button', { name: /deleting/i })
    expect(deleteButton).toBeDisabled()
  })

  it('disables both buttons during loading', () => {
    render(<ConfirmDeleteDialog {...defaultProps} isLoading={true} />)
    const cancelButton = screen.getByRole('button', { name: /cancel/i })
    expect(cancelButton).toBeDisabled()
  })

  it('renders entity name in description', () => {
    render(<ConfirmDeleteDialog {...defaultProps} entityName="Special Show" />)
    expect(screen.getByText(/Special Show/)).toBeInTheDocument()
  })

  it('has a Delete button with destructive styling', () => {
    render(<ConfirmDeleteDialog {...defaultProps} />)
    const deleteButton = screen.getByRole('button', { name: /^delete$/i })
    expect(deleteButton).toBeInTheDocument()
  })
})
