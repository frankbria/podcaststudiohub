"use client"

export function AudioPlayerSkeleton() {
	return (
		<div className="space-y-4" role="status" aria-label="Loading audio player">
			<div className="bg-gray-100 rounded p-4" aria-hidden="true">
				<div className="h-2 bg-gray-200 rounded-full animate-pulse mb-2" />
				<div className="h-8 bg-gray-200 rounded animate-pulse" />
			</div>
			<div className="flex gap-2" aria-hidden="true">
				<div className="h-10 bg-gray-200 rounded flex-1 animate-pulse" />
				<div className="h-10 bg-gray-200 rounded flex-1 animate-pulse" />
			</div>
		</div>
	)
}
