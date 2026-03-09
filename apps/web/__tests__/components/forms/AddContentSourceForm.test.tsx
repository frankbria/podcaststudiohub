import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import * as React from "react"
import { AddContentSourceForm } from "@/components/forms/AddContentSourceForm"

describe("AddContentSourceForm", () => {
	it("renders URL and Text toggle buttons", () => {
		render(<AddContentSourceForm onSubmit={jest.fn()} />)
		expect(screen.getByRole("button", { name: /^url$/i })).toBeInTheDocument()
		expect(screen.getByRole("button", { name: /^text$/i })).toBeInTheDocument()
	})

	it("shows URL input by default", () => {
		render(<AddContentSourceForm onSubmit={jest.fn()} />)
		expect(screen.getByLabelText(/^url/i)).toBeInTheDocument()
	})

	it("switches to text input when Text button clicked", async () => {
		const user = userEvent.setup()
		render(<AddContentSourceForm onSubmit={jest.fn()} />)

		await user.click(screen.getByRole("button", { name: /^text$/i }))

		await waitFor(() => {
			expect(screen.getByLabelText(/text content/i)).toBeInTheDocument()
		})
	})

	it("submit button is disabled initially", () => {
		render(<AddContentSourceForm onSubmit={jest.fn()} />)
		expect(
			screen.getByRole("button", { name: /add content/i })
		).toBeDisabled()
	})

	it("shows URL error after blurring empty URL field", async () => {
		const user = userEvent.setup()
		render(<AddContentSourceForm onSubmit={jest.fn()} />)

		const urlInput = screen.getByLabelText(/^url/i)
		await user.click(urlInput)
		await user.tab()

		await waitFor(() => {
			expect(screen.getByRole("alert")).toBeInTheDocument()
		})
	})

	it("shows error for invalid URL format", async () => {
		const user = userEvent.setup()
		render(<AddContentSourceForm onSubmit={jest.fn()} />)

		const urlInput = screen.getByLabelText(/^url/i)
		await user.type(urlInput, "not-a-url")
		await user.tab()

		await waitFor(() => {
			expect(screen.getByText(/http or https/i)).toBeInTheDocument()
		})
	})

	it("enables submit button with valid https URL", async () => {
		const user = userEvent.setup()
		render(<AddContentSourceForm onSubmit={jest.fn()} />)

		await user.type(
			screen.getByLabelText(/^url/i),
			"https://example.com/article"
		)
		await user.tab()

		await waitFor(() => {
			expect(
				screen.getByRole("button", { name: /add content/i })
			).not.toBeDisabled()
		})
	})

	it("calls onSubmit with URL data when valid", async () => {
		const onSubmit = jest.fn().mockResolvedValue(undefined)
		const user = userEvent.setup()
		render(<AddContentSourceForm onSubmit={onSubmit} />)

		await user.type(
			screen.getByLabelText(/^url/i),
			"https://example.com/article"
		)
		await user.tab()

		await waitFor(() => {
			expect(
				screen.getByRole("button", { name: /add content/i })
			).not.toBeDisabled()
		})

		await user.click(screen.getByRole("button", { name: /add content/i }))

		await waitFor(() => {
			expect(onSubmit).toHaveBeenCalledWith(
				expect.objectContaining({
					sourceType: "url",
					url: "https://example.com/article",
				})
			)
		})
	})

	it("shows text content error when text is too short", async () => {
		const user = userEvent.setup()
		render(<AddContentSourceForm onSubmit={jest.fn()} />)

		await user.click(screen.getByRole("button", { name: /^text$/i }))

		await waitFor(() =>
			expect(screen.getByLabelText(/text content/i)).toBeInTheDocument()
		)

		await user.type(screen.getByLabelText(/text content/i), "short")
		await user.tab()

		await waitFor(() => {
			expect(screen.getByText(/10 characters/i)).toBeInTheDocument()
		})
	})

	it("calls onSubmit with text data when valid content provided", async () => {
		const onSubmit = jest.fn().mockResolvedValue(undefined)
		const user = userEvent.setup()
		render(<AddContentSourceForm onSubmit={onSubmit} />)

		await user.click(screen.getByRole("button", { name: /^text$/i }))

		await waitFor(() =>
			expect(screen.getByLabelText(/text content/i)).toBeInTheDocument()
		)

		const content = "This is some valid content for the podcast episode."
		await user.type(screen.getByLabelText(/text content/i), content)
		await user.tab()

		await waitFor(() => {
			expect(
				screen.getByRole("button", { name: /add content/i })
			).not.toBeDisabled()
		})

		await user.click(screen.getByRole("button", { name: /add content/i }))

		await waitFor(() => {
			expect(onSubmit).toHaveBeenCalledWith(
				expect.objectContaining({
					sourceType: "text",
					content,
				})
			)
		})
	})
})
