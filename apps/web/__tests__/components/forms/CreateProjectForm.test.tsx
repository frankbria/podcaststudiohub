import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import * as React from "react"
import { CreateProjectForm } from "@/components/forms/CreateProjectForm"

describe("CreateProjectForm", () => {
	it("renders title and description fields", () => {
		render(<CreateProjectForm onSubmit={jest.fn()} />)
		expect(screen.getByLabelText(/project title/i)).toBeInTheDocument()
		expect(screen.getByLabelText(/description/i)).toBeInTheDocument()
	})

	it("shows required asterisk on title", () => {
		render(<CreateProjectForm onSubmit={jest.fn()} />)
		expect(screen.getByText("*")).toBeInTheDocument()
	})

	it("renders submit button", () => {
		render(<CreateProjectForm onSubmit={jest.fn()} />)
		expect(
			screen.getByRole("button", { name: /create project/i })
		).toBeInTheDocument()
	})

	it("submit button is disabled when form is pristine (mode=onBlur, isValid=false before interaction)", () => {
		render(<CreateProjectForm onSubmit={jest.fn()} />)
		const btn = screen.getByRole("button", { name: /create project/i })
		// Before any interaction, isValid is false with onBlur mode
		expect(btn).toBeDisabled()
	})

	it("shows title error message after blurring empty title field", async () => {
		const user = userEvent.setup()
		render(<CreateProjectForm onSubmit={jest.fn()} />)

		const titleInput = screen.getByLabelText(/project title/i)
		await user.click(titleInput)
		await user.tab() // blur

		await waitFor(() => {
			expect(screen.getByRole("alert")).toBeInTheDocument()
		})
	})

	it("enables submit button after valid title is entered", async () => {
		const user = userEvent.setup()
		render(<CreateProjectForm onSubmit={jest.fn()} />)

		const titleInput = screen.getByLabelText(/project title/i)
		await user.type(titleInput, "My Podcast")
		await user.tab() // blur to trigger validation

		await waitFor(() => {
			const btn = screen.getByRole("button", { name: /create project/i })
			expect(btn).not.toBeDisabled()
		})
	})

	it("calls onSubmit with trimmed data when form is valid", async () => {
		const onSubmit = jest.fn().mockResolvedValue(undefined)
		const user = userEvent.setup()
		render(<CreateProjectForm onSubmit={onSubmit} />)

		const titleInput = screen.getByLabelText(/project title/i)
		await user.type(titleInput, "My Podcast")
		await user.tab()

		await waitFor(() => {
			expect(
				screen.getByRole("button", { name: /create project/i })
			).not.toBeDisabled()
		})

		await user.click(screen.getByRole("button", { name: /create project/i }))

		await waitFor(() => {
			expect(onSubmit).toHaveBeenCalledWith(
				expect.objectContaining({ title: "My Podcast" })
			)
		})
	})

	it("does not call onSubmit with empty title", async () => {
		const onSubmit = jest.fn()
		const user = userEvent.setup()
		render(<CreateProjectForm onSubmit={onSubmit} />)

		// Button is disabled so click won't submit
		const btn = screen.getByRole("button", { name: /create project/i })
		expect(btn).toBeDisabled()
		expect(onSubmit).not.toHaveBeenCalled()
	})

	it("shows error for description over 1000 characters", async () => {
		const user = userEvent.setup()
		render(<CreateProjectForm onSubmit={jest.fn()} />)

		const titleInput = screen.getByLabelText(/project title/i)
		await user.type(titleInput, "My Podcast")

		const descInput = screen.getByLabelText(/description/i)
		await user.type(descInput, "a".repeat(1001))
		await user.tab()

		await waitFor(() => {
			expect(
				screen.getByRole("alert")
			).toHaveTextContent(/1000 characters or less/i)
		})
	})
})
