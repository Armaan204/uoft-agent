import { useTheme } from '../hooks/useTheme'

const SunIcon = () => (
  <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <circle cx="10" cy="10" r="3.5" />
    <path d="M10 2.5v2M10 15.5v2M17.5 10h-2M4.5 10h-2M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4M15.3 15.3l-1.4-1.4M6.1 6.1L4.7 4.7" strokeLinecap="round" />
  </svg>
)

const MoonIcon = () => (
  <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <path d="M16.5 12.8A7 7 0 0 1 7.2 3.5 7 7 0 1 0 16.5 12.8Z" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

export default function ThemeToggle({ className = '', labeled = false }) {
  const { isDark, toggleTheme } = useTheme()

  return (
    <button
      type="button"
      className={`theme-toggle ${className}`}
      onClick={toggleTheme}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {isDark ? <SunIcon /> : <MoonIcon />}
      {labeled && <span>{isDark ? 'Light mode' : 'Dark mode'}</span>}
    </button>
  )
}
