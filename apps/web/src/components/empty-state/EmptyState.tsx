"use client"

import { ReactNode } from "react"
import { Button } from "@/components/ui/button"

interface EmptyStateProps {
	icon?: ReactNode
	title: string
	description: string
	action?: {
		label: string
		onClick: () => void
	}
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
	return (
		<div className="flex flex-col items-center justify-center py-12 text-center">
			{icon && (
				<div className="mb-4 text-muted-foreground" data-testid="icon-container">
					{icon}
				</div>
			)}
			<h3 className="text-lg font-semibold text-foreground mb-2">{title}</h3>
			<p className="text-muted-foreground max-w-sm mb-6">{description}</p>
			{action && (
				<Button onClick={action.onClick}>{action.label}</Button>
			)}
		</div>
	)
}
