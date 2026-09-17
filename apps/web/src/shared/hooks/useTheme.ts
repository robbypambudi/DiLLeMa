import { useSyncExternalStore } from 'react'

type Theme = 'light' | 'dark'
let theme: Theme = 'light'
const listeners = new Set<() => void>()
const subscribe = (listener: () => void) => {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

function toggleTheme() {
  theme = theme === 'light' ? 'dark' : 'light'
  document.documentElement.classList.toggle('dark', theme === 'dark')
  listeners.forEach((listener) => listener())
}

export function useTheme() {
  const current = useSyncExternalStore(subscribe, () => theme, (): Theme => 'light')
  return { theme: current, toggleTheme }
}
