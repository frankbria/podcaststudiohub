"use client"

export function AnalyticsSkeleton() {
	return (
		<div aria-label="Loading" aria-busy="true">
			<div className="flex justify-between items-center mb-8" aria-hidden="true">
				<div className="h-8 bg-muted rounded w-32 animate-pulse" />
				<div className="h-10 bg-muted rounded w-40 animate-pulse" />
			</div>
			<div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8" aria-hidden="true">
				{Array.from({ length: 3 }).map((_, i) => (
					<div key={i} className="rounded-lg border border-border p-6 space-y-3">
						<div className="h-4 bg-muted rounded w-1/2 animate-pulse" />
						<div className="h-8 bg-muted rounded w-1/3 animate-pulse" />
					</div>
				))}
			</div>
			<div className="rounded-lg border border-border p-6 space-y-3" aria-hidden="true">
				<div className="h-5 bg-muted rounded w-1/3 animate-pulse" />
				{Array.from({ length: 4 }).map((_, i) => (
					<div key={i} className="h-2 bg-muted rounded w-full animate-pulse" />
				))}
			</div>
		</div>
	)
}
