"use client"

import { useState } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { projectSchema, type ProjectFormData } from "@/lib/validation"

interface CreateProjectFormProps {
	onSubmit: (data: ProjectFormData) => Promise<void>
}

export function CreateProjectForm({ onSubmit }: CreateProjectFormProps) {
	const [isSubmitting, setIsSubmitting] = useState(false)
	const {
		register,
		handleSubmit,
		formState: { errors, isValid },
		reset,
	} = useForm<ProjectFormData>({
		resolver: zodResolver(projectSchema),
		mode: "onBlur",
	})

	const handleFormSubmit = async (data: ProjectFormData) => {
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
					Project Title <span className="text-red-500">*</span>
				</label>
				<Input
					id="title"
					type="text"
					placeholder="My Podcast"
					{...register("title")}
					aria-invalid={errors.title ? "true" : "false"}
					aria-describedby={errors.title ? "title-error" : undefined}
					className={errors.title ? "border-red-500" : ""}
				/>
				{errors.title && (
					<p id="title-error" className="text-red-500 text-sm mt-1" role="alert">
						{errors.title.message}
					</p>
				)}
			</div>

			<div>
				<label
					htmlFor="description"
					className="block text-sm font-medium text-gray-700 mb-1"
				>
					Description{" "}
					<span className="text-gray-400 font-normal">(optional)</span>
				</label>
				<Input
					id="description"
					type="text"
					placeholder="A brief description of your podcast"
					{...register("description")}
					aria-describedby={errors.description ? "description-error" : undefined}
					className={errors.description ? "border-red-500" : ""}
				/>
				{errors.description && (
					<p
						id="description-error"
						className="text-red-500 text-sm mt-1"
						role="alert"
					>
						{errors.description.message}
					</p>
				)}
				<p className="text-gray-500 text-xs mt-1">Max 1000 characters</p>
			</div>

			<Button
				type="submit"
				disabled={isSubmitting || !isValid}
				className="w-full"
			>
				{isSubmitting ? "Creating..." : "Create Project"}
			</Button>
		</form>
	)
}
