"use client"

import React, { createContext, useContext, useEffect, useSyncExternalStore } from "react"

type Theme = "light" | "dark" | "system"

interface ThemeContextType {
  theme: Theme
  setTheme: (theme: Theme) => void
  resolvedTheme: "light" | "dark"
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

// The stored choice and the OS preference are both external mutable state, so
// they are read through useSyncExternalStore: the server snapshot ("system",
// light) matches the pre-hydration DOM, and the real values take over right
// after hydration — the same first-paint story as before, minus the `mounted`
// flag. The <head> script in the root layout still sets the class before paint.
const STORAGE_KEY = "theme"
const THEME_CHANGE_EVENT = "podcastfy:theme-change"
const DARK_QUERY = "(prefers-color-scheme: dark)"

function subscribeTheme(onChange: () => void) {
  window.addEventListener("storage", onChange)
  window.addEventListener(THEME_CHANGE_EVENT, onChange)
  return () => {
    window.removeEventListener("storage", onChange)
    window.removeEventListener(THEME_CHANGE_EVENT, onChange)
  }
}

function getTheme(): Theme {
  const saved = localStorage.getItem(STORAGE_KEY)
  return saved === "light" || saved === "dark" ? saved : "system"
}

function subscribeSystemDark(onChange: () => void) {
  const mediaQuery = window.matchMedia(DARK_QUERY)
  mediaQuery.addEventListener("change", onChange)
  return () => mediaQuery.removeEventListener("change", onChange)
}

function getSystemDark() {
  return window.matchMedia(DARK_QUERY).matches
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useSyncExternalStore<Theme>(subscribeTheme, getTheme, () => "system")
  const systemDark = useSyncExternalStore(subscribeSystemDark, getSystemDark, () => false)
  const resolvedTheme = theme === "system" ? (systemDark ? "dark" : "light") : theme

  useEffect(() => {
    document.documentElement.classList.toggle("dark", resolvedTheme === "dark")
  }, [resolvedTheme])

  const setTheme = (newTheme: Theme) => {
    localStorage.setItem(STORAGE_KEY, newTheme)
    window.dispatchEvent(new Event(THEME_CHANGE_EVENT))
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider")
  }
  return context
}
