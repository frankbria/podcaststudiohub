"use client"

import type { ReactNode } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  Analytics01Icon,
  Chart01Icon,
  Download01Icon,
  PlayIcon,
  GlobeIcon,
  Loading03Icon,
} from "@hugeicons/core-free-icons"
import type {
  DeviceBreakdownData,
  EpisodeAnalyticsData,
  EpisodeAnalyticsMetrics,
  TopCountriesData,
} from "./types"

type IconData = typeof Analytics01Icon

function formatListenDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${mins}:${secs.toString().padStart(2, "0")}`
}

function isAllZeroMetrics(metrics: EpisodeAnalyticsMetrics): boolean {
  return (
    metrics.total_downloads === 0 &&
    metrics.total_plays === 0 &&
    metrics.total_streams === 0
  )
}

interface MetricTileProps {
  icon: IconData
  label: string
  value: ReactNode
}

function MetricTile(props: MetricTileProps) {
  const { icon, label, value } = props
  return (
    <div className="bg-muted rounded p-3">
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        <HugeiconsIcon icon={icon} size={14} />
        {label}
      </div>
      <p className="text-lg font-semibold text-foreground">{value}</p>
    </div>
  )
}

function MetricTiles({ metrics }: { metrics: EpisodeAnalyticsMetrics }) {
  const listen = formatListenDuration(metrics.average_listen_duration_seconds)
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
      <MetricTile icon={Download01Icon} label="Downloads" value={metrics.total_downloads} />
      <MetricTile icon={PlayIcon} label="Plays" value={metrics.total_plays} />
      <MetricTile icon={Chart01Icon} label="Streams" value={metrics.total_streams} />
      <MetricTile icon={Loading03Icon} label="Avg Listen" value={listen} />
    </div>
  )
}

function CompletionRate({ metrics }: { metrics: EpisodeAnalyticsMetrics }) {
  const percent = Math.round(metrics.completion_rate * 100)
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span className="text-muted-foreground">Completion Rate</span>
        <span className="text-foreground">{percent}%</span>
      </div>
      <Progress value={percent} aria-label="Completion rate" />
    </div>
  )
}

function renderDevice([device, count]: [string, number]) {
  return (
    <li key={device} className="flex justify-between text-sm text-muted-foreground">
      <span className="capitalize">{device}</span>
      <span>{count}</span>
    </li>
  )
}

function renderApp([app, count]: [string, number]) {
  return (
    <li key={app} className="flex justify-between text-sm text-muted-foreground">
      <span className="capitalize">{app.replace(/_/g, " ")}</span>
      <span>{count}</span>
    </li>
  )
}

function renderCountry(entry: { country: string; downloads: number }) {
  return (
    <li key={entry.country} className="flex justify-between text-sm text-muted-foreground">
      <span>{entry.country}</span>
      <span>{entry.downloads}</span>
    </li>
  )
}

function DeviceBreakdown({ devices }: { devices: DeviceBreakdownData }) {
  const rows = Object.entries(devices)
  return (
    <div>
      <p className="text-sm font-medium text-foreground mb-2">Device Breakdown</p>
      <ul className="space-y-1">{rows.map(renderDevice)}</ul>
    </div>
  )
}

function AppBreakdown({ apps }: { apps: Record<string, number> }) {
  const rows = Object.entries(apps)
  return (
    <div>
      <p className="text-sm font-medium text-foreground mb-2">App Breakdown</p>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No app data yet</p>
      ) : (
        <ul className="space-y-1">{rows.map(renderApp)}</ul>
      )}
    </div>
  )
}

function CountryRows({ countries, isEmpty }: { countries: TopCountriesData; isEmpty: boolean }) {
  const rows = countries.map(renderCountry)
  if (isEmpty) {
    return <p className="text-sm text-muted-foreground">No country data yet</p>
  }
  return <ul className="space-y-1">{rows}</ul>
}

function TopCountries({ countries }: { countries: TopCountriesData }) {
  const isEmpty = countries.length === 0
  return (
    <div>
      <p className="text-sm font-medium text-foreground mb-2 flex items-center gap-1">
        <HugeiconsIcon icon={GlobeIcon} size={16} />
        Top Countries
      </p>
      <CountryRows countries={countries} isEmpty={isEmpty} />
    </div>
  )
}

function AnalyticsDetails({ analytics }: { analytics: EpisodeAnalyticsData }) {
  const { metrics } = analytics
  return (
    <div className="space-y-4">
      <MetricTiles metrics={metrics} />
      <CompletionRate metrics={metrics} />
      <DeviceBreakdown devices={analytics.device_breakdown} />
      <AppBreakdown apps={analytics.app_breakdown} />
      <TopCountries countries={analytics.top_countries} />
    </div>
  )
}

interface AnalyticsBodyProps {
  analytics: EpisodeAnalyticsData | null
  loading: boolean
  error: boolean
}

function AnalyticsBody(props: AnalyticsBodyProps) {
  const { analytics, loading, error } = props
  if (loading) {
    return (
      <p className="text-sm text-muted-foreground flex items-center gap-2">
        <HugeiconsIcon icon={Loading03Icon} size={16} />
        Loading analytics...
      </p>
    )
  }
  if (error) return <p className="text-sm text-muted-foreground">Analytics unavailable</p>
  if (!analytics) return null
  if (isAllZeroMetrics(analytics.metrics)) {
    return <p className="text-sm text-muted-foreground">No analytics yet</p>
  }
  return <AnalyticsDetails analytics={analytics} />
}

export function AnalyticsCard(props: AnalyticsBodyProps) {
  const body = <AnalyticsBody {...props} />
  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <HugeiconsIcon icon={Analytics01Icon} size={20} />
          Analytics
        </CardTitle>
      </CardHeader>
      <CardContent>
        {body}
      </CardContent>
    </Card>
  )
}
