"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { HugeiconsIcon } from "@hugeicons/react"
import { Alert02Icon } from "@hugeicons/core-free-icons"
import { approveContentReview } from "./episode-api"
import type { ContentFlag, Episode } from "./types"

function ContentFlagItem({ flag }: { flag: ContentFlag }) {
  const turn = flag.turn + 1 // 0-based from the engine; people count from 1
  return (
    <li>
      {flag.kind}: <span className="font-mono text-foreground">{flag.match}</span>
      {" — "}
      {flag.speaker}, turn {turn}
    </li>
  )
}

function renderContentFlag(flag: ContentFlag, index: number) {
  return <ContentFlagItem key={index} flag={flag} />
}

type ReviewView = "held" | "approved" | null

// Which review UI an episode needs: a finished run that is held, or one whose
// flags were approved. A run that failed after screening produced nothing to
// publish (#576 review). Approved is only reachable from pending, which is
// only set when there are flags, so the review state alone decides.
const REVIEW_VIEWS = { pending: "held", approved: "approved" } as const

function reviewView(episode: Episode): ReviewView {
  if (episode.generation_status !== "complete") return null
  const review = episode.generation_progress?.content_review
  return review ? REVIEW_VIEWS[review] : null
}

export function ContentReviewNotice({
  episode,
  onApproved,
}: {
  episode: Episode
  onApproved: (episode: Episode) => void
}) {
  const view = reviewView(episode)
  if (view === "held") return <HeldForReview episode={episode} onApproved={onApproved} />
  if (view !== "approved") return null
  return (
    <p className="text-sm text-muted-foreground mb-4">Content flags reviewed and approved</p>
  )
}

function HeldForReview({
  episode,
  onApproved,
}: {
  episode: Episode
  onApproved: (episode: Episode) => void
}) {
  const [approving, setApproving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const flags = episode.generation_progress?.content_flags ?? []

  async function approve() {
    setApproving(true)
    setError(null)
    const result = await approveContentReview(episode.id)
    setApproving(false)
    if ("episode" in result) onApproved(result.episode)
    else setError(result.error)
  }

  return (
    <section
      role="status"
      aria-labelledby="content-review-heading"
      className="mb-4 rounded-md border border-destructive/50 bg-destructive/5 p-4 space-y-3"
    >
      <h3
        id="content-review-heading"
        className="flex items-center gap-2 font-semibold text-destructive"
      >
        <HugeiconsIcon icon={Alert02Icon} size={18} aria-hidden="true" />
        Held for review — not published
      </h3>
      <p className="text-sm text-foreground">
        The script mentions things its sources don&apos;t support, which may be injected
        promotion. It is kept out of the RSS feed and platform distribution until you
        approve it.
      </p>
      <ul className="text-sm text-muted-foreground list-disc pl-5 space-y-1">
        {flags.map(renderContentFlag)}
      </ul>
      {error && (
        <p className="text-sm text-destructive" role="alert">
          Failed to approve: {error}
        </p>
      )}
      <Button onClick={approve} disabled={approving} size="sm">
        {approving ? "Approving..." : "Approve for publishing"}
      </Button>
    </section>
  )
}
