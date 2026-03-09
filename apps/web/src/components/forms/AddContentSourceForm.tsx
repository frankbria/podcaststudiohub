"use client"

import { useState } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { contentSourceSchema, type ContentSourceData } from "@/lib/validation"

interface AddContentSourceFormProps {
	onSubmit: (data: ContentSourceData) => Promise<void>
}

export function AddContentSourceForm({ onSubmit }: AddContentSourceFormProps) {
	const [isSubmitting, setIsSubmitting] = useState(false)
	const {
		register,
		handleSubmit,
		watch,
		setValue,
		trigger,
		formState: { errors, isValid },
		reset,
	} = useForm<ContentSourceData>({
		resolver: zodResolver(contentSourceSchema),
		mode: "onBlur",
		defaultValues: {
			sourceType: "url",
		},
	})

	const sourceType = watch("sourceType")

	const switchSourceType = (type: "url" | "text") => {
		setValue("sourceType", type, { shouldValidate: false })
		setValue("url", "")
		setValue("content", "")
		trigger()
	}

	const handleFormSubmit = async (data: ContentSourceData) => {
		if (isSubmitting) return
		setIsSubmitting(true)
		try {
			await onSubmit(data)
			reset({ sourceType: "url" })
		} finally {
			setIsSubmitting(false)
		}
	}

	return (
		<form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-4">
			<div>
				<label className="block text-sm font-medium text-gray-700 mb-2">
					Content Type
				</label>
				<div className="flex gap-2">
					<Button
						type="button"
						variant={sourceType === "url" ? "default" : "outline"}
						onClick={() => switchSourceType("url")}
						className="flex-1"
					>
						URL
					</Button>
					<Button
						type="button"
						variant={sourceType === "text" ? "default" : "outline"}
						onClick={() => switchSourceType("text")}
						className="flex-1"
					>
						Text
					</Button>
				</div>
			</div>

			{sourceType === "url" ? (
				<div>
					<label
						htmlFor="url"
						className="block text-sm font-medium text-gray-700 mb-1"
					>
						URL <span className="text-red-500">*</span>
					</label>
					<Input
						id="url"
						type="url"
						placeholder="https://example.com/article"
						{...register("url")}
						aria-invalid={errors.url ? "true" : "false"}
						aria-describedby={errors.url ? "url-error" : undefined}
						className={errors.url ? "border-red-500" : ""}
					/>
					{errors.url && (
						<p id="url-error" className="text-red-500 text-sm mt-1" role="alert">
							{errors.url.message}
						</p>
					)}
					<p className="text-gray-500 text-xs mt-1">
						Supports HTTP and HTTPS URLs
					</p>
				</div>
			) : (
				<div>
					<label
						htmlFor="content"
						className="block text-sm font-medium text-gray-700 mb-1"
					>
						Text Content <span className="text-red-500">*</span>
					</label>
					<textarea
						id="content"
						className={`w-full h-32 p-2 border rounded text-sm ${errors.content ? "border-red-500" : "border-gray-300"}`}
						placeholder="Paste your content here..."
						{...register("content")}
						aria-invalid={errors.content ? "true" : "false"}
						aria-describedby={errors.content ? "content-error" : undefined}
					/>
					{errors.content && (
						<p
							id="content-error"
							className="text-red-500 text-sm mt-1"
							role="alert"
						>
							{errors.content.message}
						</p>
					)}
					<p className="text-gray-500 text-xs mt-1">10 – 50,000 characters</p>
				</div>
			)}

			<Button
				type="submit"
				disabled={isSubmitting || !isValid}
				className="w-full"
			>
				{isSubmitting ? "Adding..." : "Add Content"}
			</Button>
		</form>
	)
}
