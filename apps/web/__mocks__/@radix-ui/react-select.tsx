import * as React from 'react'

interface RootProps {
  children: React.ReactNode
  defaultValue?: string
  value?: string
  onValueChange?: (value: string) => void
}

const RootContext = React.createContext<{
  open: boolean
  setOpen: (open: boolean) => void
  value: string
  setValue: (value: string) => void
  onValueChange?: (value: string) => void
}>({ open: false, setOpen: () => {}, value: '', setValue: () => {} })

const Root = ({ children, defaultValue = '', value: controlledValue, onValueChange }: RootProps) => {
  const [open, setOpen] = React.useState(false)
  const [value, setValue] = React.useState(controlledValue ?? defaultValue)
  return (
    <RootContext.Provider value={{ open, setOpen, value, setValue, onValueChange }}>
      <div data-value={value}>{children}</div>
    </RootContext.Provider>
  )
}

const Trigger = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement>>(
  ({ children, className, ...props }, ref) => {
    const { open, setOpen } = React.useContext(RootContext)
    return (
      <button
        ref={ref}
        role="combobox"
        aria-expanded={open}
        className={className}
        onClick={() => setOpen(!open)}
        {...props}
      >
        {children}
      </button>
    )
  }
)
Trigger.displayName = 'SelectTrigger'

const Value = ({ placeholder }: { placeholder?: string }) => {
  const { value } = React.useContext(RootContext)
  return <span>{value || placeholder}</span>
}

const Icon = ({ children }: { children?: React.ReactNode; asChild?: boolean }) => <span>{children}</span>

const Portal = ({ children }: { children: React.ReactNode }) => <>{children}</>

const Content = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { position?: string }
>(({ children, className, position = 'popper', ...props }, ref) => {
  const { open } = React.useContext(RootContext)
  if (!open) return null
  return (
    <div ref={ref} className={className} data-position={position} role="listbox" {...props}>
      {children}
    </div>
  )
})
Content.displayName = 'SelectContent'

const Viewport = ({ children, className }: { children: React.ReactNode; className?: string }) => (
  <div className={className}>{children}</div>
)

const Group = ({ children }: { children: React.ReactNode }) => <div role="group">{children}</div>

const Label = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ children, className, ...props }, ref) => (
    <div ref={ref} className={className} {...props}>
      {children}
    </div>
  )
)
Label.displayName = 'SelectLabel'

const Item = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { value: string }
>(({ children, className, value: itemValue, ...props }, ref) => {
  const { setValue, onValueChange, setOpen } = React.useContext(RootContext)
  return (
    <div
      ref={ref}
      role="option"
      className={className}
      onClick={() => {
        setValue(itemValue)
        onValueChange?.(itemValue)
        setOpen(false)
      }}
      {...props}
    >
      {children}
    </div>
  )
})
Item.displayName = 'SelectItem'

const ItemText = ({ children }: { children: React.ReactNode }) => <span>{children}</span>

const ItemIndicator = ({ children }: { children?: React.ReactNode }) => <span>{children}</span>

const Separator = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={className} role="separator" {...props} />
  )
)
Separator.displayName = 'SelectSeparator'

const ScrollUpButton = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ children, className, ...props }, ref) => (
    <div ref={ref} className={className} {...props}>
      {children}
    </div>
  )
)
ScrollUpButton.displayName = 'SelectScrollUpButton'

const ScrollDownButton = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ children, className, ...props }, ref) => (
    <div ref={ref} className={className} {...props}>
      {children}
    </div>
  )
)
ScrollDownButton.displayName = 'SelectScrollDownButton'

export {
  Root,
  Trigger,
  Value,
  Icon,
  Portal,
  Content,
  Viewport,
  Group,
  Label,
  Item,
  ItemText,
  ItemIndicator,
  Separator,
  ScrollUpButton,
  ScrollDownButton,
}
