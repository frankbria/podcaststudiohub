"use client"

export function DistributionSkeleton() {
	return (
		<div className="min-h-screen bg-background p-8" aria-label="Loading" aria-busy="true">
			<div className="max-w-6xl mx-auto">
				<div className="flex justify-between items-center mb-6">
					<div className="h-10 bg-muted rounded w-48 animate-pulse" />
					<div className="h-10 bg-muted rounded w-72 animate-pulse" />
				</div>

				<div className="rounded-lg border border-border p-6 mb-8 space-y-2" aria-hidden="true">
					<div className="h-5 bg-muted rounded w-1/3 animate-pulse" />
					<div className="h-4 bg-muted rounded w-full animate-pulse" />
				</div>

				<div className="space-y-4">
					{Array.from({ length: 3 }).map((_, i) => (
						<div key={i} className="rounded-lg border border-border p-6 space-y-3" aria-hidden="true">
							<div className="h-5 bg-muted rounded w-1/3 animate-pulse" />
							<div className="h-4 bg-muted rounded w-1/4 animate-pulse" />
							<div className="flex gap-2 pt-2">
								<div className="h-8 bg-muted rounded w-28 animate-pulse" />
								<div className="h-8 bg-muted rounded w-28 animate-pulse" />
								<div className="h-8 bg-muted rounded w-10 animate-pulse" />
							</div>
						</div>
					))}
				</div>
			</div>
		</div>
	)
}
