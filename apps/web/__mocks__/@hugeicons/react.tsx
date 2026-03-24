import * as React from 'react'

export const HugeiconsIcon = ({
  icon,
  size = 24,
  color,
  className,
  strokeWidth,
  ...props
}: {
  icon: unknown
  size?: number
  color?: string
  className?: string
  strokeWidth?: number
  [key: string]: unknown
}) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color || 'currentColor'}
    strokeWidth={strokeWidth || 1.5}
    className={className}
    data-testid="hugeicons-icon"
    {...props}
  />
)
