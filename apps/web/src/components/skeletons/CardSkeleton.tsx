"use client"

export function CardSkeleton() {
	return (
		<div className="rounded-lg border border-gray-200 p-6 space-y-4" aria-hidden="true">
			<div className="h-6 bg-gray-200 rounded w-3/4 animate-pulse" />
			<div className="h-4 bg-gray-200 rounded w-full animate-pulse" />
			<div className="h-4 bg-gray-200 rounded w-5/6 animate-pulse" />
			<div className="flex gap-2 pt-2">
				<div className="h-8 bg-gray-200 rounded flex-1 animate-pulse" />
				<div className="h-8 bg-gray-200 rounded flex-1 animate-pulse" />
			</div>
		</div>
	)
}
