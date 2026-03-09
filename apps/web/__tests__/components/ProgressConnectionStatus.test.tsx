import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { ProgressConnectionStatus } from '@/components/ProgressConnectionStatus'
import type { ConnectionStatus } from '@/lib/event-source-client'

describe('ProgressConnectionStatus', () => {
  it('renders nothing when status is "complete"', () => {
    const { container } = render(<ProgressConnectionStatus status="complete" />)
    expect(container.firstChild).toBeNull()
  })

  it('shows "Connecting..." text for connecting status', () => {
    render(<ProgressConnectionStatus status="connecting" />)
    expect(screen.getByText('Connecting...')).toBeInTheDocument()
  })

  it('shows "Connected" text for connected status', () => {
    render(<ProgressConnectionStatus status="connected" />)
    expect(screen.getByText('Connected')).toBeInTheDocument()
  })

  it('shows "Reconnecting..." text for reconnecting status', () => {
    render(<ProgressConnectionStatus status="reconnecting" />)
    expect(screen.getByText('Reconnecting...')).toBeInTheDocument()
  })

  it('shows error text for error status', () => {
    render(<ProgressConnectionStatus status="error" />)
    expect(screen.getByText('Connection lost, retrying...')).toBeInTheDocument()
  })

  it('shows polling text for polling status', () => {
    render(<ProgressConnectionStatus status="polling" />)
    expect(screen.getByText('Using polling mode')).toBeInTheDocument()
  })

  it('has role="status" for accessibility', () => {
    render(<ProgressConnectionStatus status="connecting" />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  const VISIBLE_STATUSES: ConnectionStatus[] = [
    'connecting',
    'connected',
    'reconnecting',
    'error',
    'polling',
  ]

  it.each(VISIBLE_STATUSES)('renders visible element for status "%s"', (status) => {
    const { container } = render(<ProgressConnectionStatus status={status} />)
    expect(container.firstChild).not.toBeNull()
  })
})
