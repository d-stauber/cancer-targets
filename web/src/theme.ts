import { createContext, useContext, useEffect, useState } from 'react'

export type Theme = 'light' | 'dark'
const KEY = 'ct-theme'

export function getTheme(): Theme {
  try { const t = localStorage.getItem(KEY); if (t === 'light' || t === 'dark') return t } catch {}
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}
export function applyTheme(t: Theme) {
  document.documentElement.setAttribute('data-theme', t)
  try { localStorage.setItem(KEY, t) } catch {}
}
export function useTheme(): [Theme, () => void] {
  const [t, setT] = useState<Theme>(getTheme)
  useEffect(() => { applyTheme(t) }, [t])
  return [t, () => setT(t === 'dark' ? 'light' : 'dark')]
}
/** Read a CSS custom property from :root (for Plotly colors). */
export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}
export function plotTheme() {
  return {
    paper: cssVar('--surface'), plot: cssVar('--surface'), text: cssVar('--text-2'), textStrong: cssVar('--text'),
    grid: cssVar('--border'), axis: cssVar('--border-2'), s1: cssVar('--s1'), s2: cssVar('--s2'), s3: cssVar('--s3'), s7: cssVar('--s7'),
    neutral: cssVar('--neutral-mark'), font: cssVar('--font'),
  }
}

/** Current theme for components that read CSS variables at render time (e.g. Plotly). */
export const ThemeContext = createContext<Theme>('light')
export const useCurrentTheme = () => useContext(ThemeContext)
