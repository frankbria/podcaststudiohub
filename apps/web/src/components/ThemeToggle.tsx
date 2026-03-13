"use client"

import React from "react"
import { useTheme } from "@/components/providers/theme-provider"
import { Button } from "@/components/ui/button"
import { Sun, Moon, Monitor } from "lucide-react"

type Theme = "light" | "dark" | "system"

const THEME_CYCLE: Theme[] = ["system", "light", "dark"]

const THEME_ICONS: Record<Theme, React.ReactNode> = {
	light: <Sun className="h-5 w-5" />,
	dark: <Moon className="h-5 w-5" />,
	system: <Monitor className="h-5 w-5" />,
}

const THEME_LABELS: Record<Theme, string> = {
	light: "Switch to dark mode",
	dark: "Switch to system theme",
	system: "Switch to light mode",
}

export function ThemeToggle() {
	const { theme, setTheme } = useTheme()

	const handleClick = () => {
		const currentIndex = THEME_CYCLE.indexOf(theme)
		const nextIndex = (currentIndex + 1) % THEME_CYCLE.length
		setTheme(THEME_CYCLE[nextIndex])
	}

	return (
		<Button
			variant="ghost"
			size="icon"
			aria-label={`Toggle theme (current: ${theme})`}
			title={THEME_LABELS[theme]}
			onClick={handleClick}
			className="rounded-full"
		>
			{THEME_ICONS[theme]}
		</Button>
	)
}
