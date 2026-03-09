import type { ConnectionStatus } from '@/lib/event-source-client'

interface ProgressConnectionStatusProps {
  status: ConnectionStatus
}

interface StatusConfig {
  icon: string
  text: string
  color: string
  bg: string
}

const STATUS_CONFIG: Record<ConnectionStatus, StatusConfig> = {
  connecting: {
    icon: '⟳',
    text: 'Connecting...',
    color: 'text-blue-600',
    bg: 'bg-blue-50',
  },
  connected: {
    icon: '●',
    text: 'Connected',
    color: 'text-green-600',
    bg: 'bg-green-50',
  },
  reconnecting: {
    icon: '⟳',
    text: 'Reconnecting...',
    color: 'text-yellow-600',
    bg: 'bg-yellow-50',
  },
  error: {
    icon: '⚠',
    text: 'Connection lost, retrying...',
    color: 'text-red-600',
    bg: 'bg-red-50',
  },
  polling: {
    icon: '⟳',
    text: 'Using polling mode',
    color: 'text-orange-600',
    bg: 'bg-orange-50',
  },
  complete: {
    icon: '✓',
    text: 'Generation complete',
    color: 'text-green-600',
    bg: 'bg-green-50',
  },
}

/**
 * Displays the current SSE / polling connection status during episode generation.
 * Only rendered while generation is active (status !== 'complete').
 */
export function ProgressConnectionStatus({ status }: ProgressConnectionStatusProps) {
  if (status === 'complete') return null

  const cfg = STATUS_CONFIG[status]

  return (
    <div
      className={`p-2 rounded flex items-center gap-2 ${cfg.bg}`}
      role="status"
      aria-live="polite"
    >
      <span className={`${cfg.color} text-sm`} aria-hidden="true">
        {cfg.icon}
      </span>
      <span className={`text-sm font-medium ${cfg.color}`}>{cfg.text}</span>
    </div>
  )
}
