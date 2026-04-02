"use client"

export function EpisodeListSkeleton() {
	return (
		<div className="space-y-4" aria-label="Loading" aria-busy="true">
			{Array.from({ length: 4 }).map((_, i) => (
				<div key={i} className="rounded-lg border border-border p-6 space-y-3" aria-hidden="true">
					<div className="h-5 bg-muted rounded w-2/3 animate-pulse" />
					<div className="h-4 bg-muted rounded w-full animate-pulse" />
					<div className="flex justify-between items-center">
						<div className="h-4 bg-muted rounded w-1/4 animate-pulse" />
						<div className="h-6 bg-muted rounded w-1/5 animate-pulse" />
					</div>
				</div>
			))}
		</div>
	)
}
