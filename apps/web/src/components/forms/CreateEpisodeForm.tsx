"use client"

import { useState } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { episodeSchema, type EpisodeFormData } from "@/lib/validation"

interface CreateEpisodeFormProps {
	onSubmit: (data: EpisodeFormData) => Promise<void>
}

export function CreateEpisodeForm({ onSubmit }: CreateEpisodeFormProps) {
	const [isSubmitting, setIsSubmitting] = useState(false)
	const {
		register,
		handleSubmit,
		formState: { errors, isValid },
		reset,
	} = useForm<EpisodeFormData>({
		resolver: zodResolver(episodeSchema),
		mode: "onBlur",
	})

	const handleFormSubmit = async (data: EpisodeFormData) => {
		if (isSubmitting) return
		setIsSubmitting(true)
		try {
			await onSubmit(data)
			reset()
		} finally {
			setIsSubmitting(false)
		}
	}

	return (
		<form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-4">
			<div>
				<label
					htmlFor="title"
					className="block text-sm font-medium text-gray-700 mb-1"
				>
					Episode Title <span className="text-red-500">*</span>
				</label>
				<Input
					id="title"
					type="text"
					placeholder="Episode 1: Introduction"
					{...register("title")}
					aria-invalid={errors.title ? "true" : "false"}
					aria-describedby={errors.title ? "episode-title-error" : undefined}
					className={errors.title ? "border-red-500" : ""}
				/>
				{errors.title && (
					<p
						id="episode-title-error"
						className="text-red-500 text-sm mt-1"
						role="alert"
					>
						{errors.title.message}
					</p>
				)}
			</div>

			<Button
				type="submit"
				disabled={isSubmitting || !isValid}
				className="w-full"
			>
				{isSubmitting ? "Creating..." : "Create Episode"}
			</Button>
		</form>
	)
}
