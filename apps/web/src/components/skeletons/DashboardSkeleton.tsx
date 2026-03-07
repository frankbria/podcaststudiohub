"use client"

import { CardSkeleton } from "./CardSkeleton"

export function DashboardSkeleton() {
	return (
		<div className="min-h-screen bg-gray-50 p-8" role="status" aria-label="Loading projects">
			<div className="max-w-6xl mx-auto">
				<div className="flex justify-between items-center mb-8">
					<div className="h-10 bg-gray-200 rounded w-48 animate-pulse" aria-hidden="true" />
					<div className="h-10 bg-gray-200 rounded w-32 animate-pulse" aria-hidden="true" />
				</div>

				<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
					{Array.from({ length: 6 }).map((_, i) => (
						<CardSkeleton key={i} />
					))}
				</div>
			</div>
		</div>
	)
}
