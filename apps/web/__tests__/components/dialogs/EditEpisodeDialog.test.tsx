import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { EditEpisodeDialog } from '@/components/dialogs/EditEpisodeDialog'

const mockEpisode = {
  id: 'episode-1',
  title: 'Episode 1',
  description: 'An intro episode',
  generation_status: 'draft',
  created_at: '2024-01-01T00:00:00Z',
}

describe('EditEpisodeDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: jest.fn(),
    episode: mockEpisode,
    onUpdate: jest.fn(),
    onSave: jest.fn().mockResolvedValue(undefined),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders dialog when open is true', () => {
    render(<EditEpisodeDialog {...defaultProps} />)
    expect(screen.getByText(/edit episode/i)).toBeInTheDocument()
  })

  it('does not render when open is false', () => {
    render(<EditEpisodeDialog {...defaultProps} open={false} />)
    expect(screen.queryByText(/edit episode/i)).not.toBeInTheDocument()
  })

  it('pre-populates form fields with episode data', () => {
    render(<EditEpisodeDialog {...defaultProps} />)
    const titleInput = screen.getByDisplayValue('Episode 1')
    expect(titleInput).toBeInTheDocument()
    const descriptionInput = screen.getByDisplayValue('An intro episode')
    expect(descriptionInput).toBeInTheDocument()
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const onOpenChange = jest.fn()
    render(<EditEpisodeDialog {...defaultProps} onOpenChange={onOpenChange} />)
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('calls onSave with updated values when form is submitted', async () => {
    const user = userEvent.setup()
    const onSave = jest.fn().mockResolvedValue(undefined)
    render(<EditEpisodeDialog {...defaultProps} onSave={onSave} />)

    const titleInput = screen.getByDisplayValue('Episode 1')
    await user.clear(titleInput)
    await user.type(titleInput, 'New Title')

    await user.click(screen.getByRole('button', { name: /update/i }))
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'New Title' })
    )
  })

  it('disables submit button when title is empty', async () => {
    const user = userEvent.setup()
    render(<EditEpisodeDialog {...defaultProps} />)
    const titleInput = screen.getByDisplayValue('Episode 1')
    await user.clear(titleInput)
    const submitButton = screen.getByRole('button', { name: /update/i })
    expect(submitButton).toBeDisabled()
  })

  it('shows loading state when isLoading is true', () => {
    render(<EditEpisodeDialog {...defaultProps} isLoading={true} />)
    const updateButton = screen.getByRole('button', { name: /updating/i })
    expect(updateButton).toBeDisabled()
  })
})
