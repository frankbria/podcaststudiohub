import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import * as React from "react"
import { CreateEpisodeForm } from "@/components/forms/CreateEpisodeForm"

describe("CreateEpisodeForm", () => {
	it("renders title field", () => {
		render(<CreateEpisodeForm onSubmit={jest.fn()} />)
		expect(screen.getByLabelText(/episode title/i)).toBeInTheDocument()
	})

	it("renders submit button", () => {
		render(<CreateEpisodeForm onSubmit={jest.fn()} />)
		expect(
			screen.getByRole("button", { name: /create episode/i })
		).toBeInTheDocument()
	})

	it("submit button is disabled when title is empty", () => {
		render(<CreateEpisodeForm onSubmit={jest.fn()} />)
		expect(
			screen.getByRole("button", { name: /create episode/i })
		).toBeDisabled()
	})

	it("shows error after blurring empty title field", async () => {
		const user = userEvent.setup()
		render(<CreateEpisodeForm onSubmit={jest.fn()} />)

		const titleInput = screen.getByLabelText(/episode title/i)
		await user.click(titleInput)
		await user.tab()

		await waitFor(() => {
			expect(screen.getByRole("alert")).toBeInTheDocument()
		})
	})

	it("enables submit button after valid title entered", async () => {
		const user = userEvent.setup()
		render(<CreateEpisodeForm onSubmit={jest.fn()} />)

		await user.type(screen.getByLabelText(/episode title/i), "Episode 1")
		await user.tab()

		await waitFor(() => {
			expect(
				screen.getByRole("button", { name: /create episode/i })
			).not.toBeDisabled()
		})
	})

	it("calls onSubmit with correct data", async () => {
		const onSubmit = jest.fn().mockResolvedValue(undefined)
		const user = userEvent.setup()
		render(<CreateEpisodeForm onSubmit={onSubmit} />)

		await user.type(screen.getByLabelText(/episode title/i), "My Episode")
		await user.tab()

		await waitFor(() => {
			expect(
				screen.getByRole("button", { name: /create episode/i })
			).not.toBeDisabled()
		})

		await user.click(screen.getByRole("button", { name: /create episode/i }))

		await waitFor(() => {
			expect(onSubmit).toHaveBeenCalledWith(
				expect.objectContaining({ title: "My Episode" })
			)
		})
	})
})
