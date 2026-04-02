"use client"

export function CardSkeleton() {
	return (
		<div className="rounded-lg border border-border p-6 space-y-4" aria-hidden="true">
			<div className="h-6 bg-muted rounded w-3/4 animate-pulse" />
			<div className="h-4 bg-muted rounded w-full animate-pulse" />
			<div className="h-4 bg-muted rounded w-5/6 animate-pulse" />
			<div className="flex gap-2 pt-2">
				<div className="h-8 bg-muted rounded flex-1 animate-pulse" />
				<div className="h-8 bg-muted rounded flex-1 animate-pulse" />
			</div>
		</div>
	)
}
