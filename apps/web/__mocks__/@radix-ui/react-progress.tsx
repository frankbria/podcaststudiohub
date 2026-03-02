import * as React from 'react'

const Root = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { value?: number }
>(({ children, className, value, ...props }, ref) => (
  <div
    ref={ref}
    role="progressbar"
    aria-valuenow={value}
    className={className}
    {...props}
  >
    {children}
  </div>
))
Root.displayName = 'ProgressRoot'

const Indicator = ({
  className,
  style,
}: {
  className?: string
  style?: React.CSSProperties
}) => <div className={className} style={style} data-testid="progress-indicator" />

export { Root, Indicator }
