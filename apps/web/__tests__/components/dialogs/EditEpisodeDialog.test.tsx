import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { EditEpisodeDialog } from '@/components/dialogs/EditEpisodeDialog'

const mockEpisode = {
  id: 'episode-1',
  title: 'Episode 1: Introduction',
  description: null,
}

describe('EditEpisodeDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: jest.fn(),
    episode: mockEpisode,
    onUpdate: jest.fn().mockResolvedValue(undefined),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders with pre-populated episode title', () => {
    render(<EditEpisodeDialog {...defaultProps} />)
    expect(screen.getByDisplayValue('Episode 1: Introduction')).toBeInTheDocument()
  })

  it('renders Edit Episode title', () => {
    render(<EditEpisodeDialog {...defaultProps} />)
    expect(screen.getByText('Edit Episode')).toBeInTheDocument()
  })

  it('shows validation error when title is cleared', async () => {
    const user = userEvent.setup()
    render(<EditEpisodeDialog {...defaultProps} />)
    const titleInput = screen.getByDisplayValue('Episode 1: Introduction')
    await user.clear(titleInput)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('calls onUpdate with updated title on submit', async () => {
    const user = userEvent.setup()
    render(<EditEpisodeDialog {...defaultProps} />)
    const titleInput = screen.getByDisplayValue('Episode 1: Introduction')
    await user.clear(titleInput)
    await user.type(titleInput, 'New Episode Title')
    await user.click(screen.getByRole('button', { name: /^update$/i }))
    await waitFor(() => {
      expect(defaultProps.onUpdate).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'New Episode Title' })
      )
    })
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<EditEpisodeDialog {...defaultProps} />)
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })

  it('does not render content when closed', () => {
    render(<EditEpisodeDialog {...defaultProps} open={false} />)
    expect(screen.queryByText('Edit Episode')).not.toBeInTheDocument()
  })
})
