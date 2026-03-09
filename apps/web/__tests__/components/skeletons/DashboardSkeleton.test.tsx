import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { DashboardSkeleton } from '@/components/skeletons/DashboardSkeleton'

describe('DashboardSkeleton', () => {
  it('renders the dashboard skeleton container', () => {
    render(<DashboardSkeleton />)
    expect(screen.getByTestId('dashboard-skeleton')).toBeInTheDocument()
  })

  it('announces loading state to screen readers', () => {
    render(<DashboardSkeleton />)
    expect(screen.getByLabelText('Loading')).toBeInTheDocument()
  })

  it('renders 6 card skeletons', () => {
    render(<DashboardSkeleton />)
    expect(screen.getAllByTestId('card-skeleton')).toHaveLength(6)
  })
})
