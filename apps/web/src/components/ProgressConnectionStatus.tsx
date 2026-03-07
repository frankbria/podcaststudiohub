import { ConnectionStatus } from "@/lib/event-source-client"

interface ProgressConnectionStatusProps {
  status: ConnectionStatus
}

const STATUS_CONFIG: Record<
  ConnectionStatus,
  { icon: string; text: string; color: string; bg: string }
> = {
  connecting: {
    icon: "⟳",
    text: "Connecting...",
    color: "text-blue-600",
    bg: "bg-blue-50",
  },
  connected: {
    icon: "●",
    text: "Connected",
    color: "text-green-600",
    bg: "bg-green-50",
  },
  reconnecting: {
    icon: "⟳",
    text: "Reconnecting...",
    color: "text-yellow-600",
    bg: "bg-yellow-50",
  },
  error: {
    icon: "⚠",
    text: "Connection lost, retrying...",
    color: "text-red-600",
    bg: "bg-red-50",
  },
  polling: {
    icon: "⟳",
    text: "Using polling mode",
    color: "text-orange-600",
    bg: "bg-orange-50",
  },
  complete: {
    icon: "✓",
    text: "Generation complete",
    color: "text-green-600",
    bg: "bg-green-50",
  },
}

export function ProgressConnectionStatus({ status }: ProgressConnectionStatusProps) {
  const config = STATUS_CONFIG[status]

  return (
    <div
      className={`p-2 rounded ${config.bg} flex items-center gap-2`}
      data-testid="connection-status"
      role="status"
      aria-label={config.text}
    >
      <span className={`${config.color} text-xs`} aria-hidden="true">
        {config.icon}
      </span>
      <span className={`text-xs font-medium ${config.color}`}>{config.text}</span>
    </div>
  )
}
