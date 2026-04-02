"use client"

export function AudioPlayerSkeleton() {
	return (
		<div className="space-y-4" aria-label="Loading" aria-busy="true">
			<div className="bg-muted rounded p-4" aria-hidden="true">
				<div className="h-2 bg-muted-foreground/20 rounded-full animate-pulse mb-2" />
				<div className="h-8 bg-muted-foreground/20 rounded animate-pulse" />
			</div>
			<div className="flex gap-2" aria-hidden="true">
				<div className="h-10 bg-muted rounded flex-1 animate-pulse" />
				<div className="h-10 bg-muted rounded flex-1 animate-pulse" />
			</div>
		</div>
	)
}
