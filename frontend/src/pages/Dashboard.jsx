import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import client from '../api/client'
import AnnouncementList from '../components/AnnouncementList'
import CourseCard from '../components/CourseCard'
import DeadlineList from '../components/DeadlineList'

const DASHBOARD_STALE_TIME_MS = 5 * 60 * 1000


async function fetchDashboard(forceRefresh = false) {
  const url = forceRefresh ? '/api/courses/dashboard?force_refresh=true' : '/api/courses/dashboard'
  const response = await client.get(url)
  return response.data
}

function formatAge(isoString) {
  if (!isoString) return null
  const diffMs = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diffMs / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return hours === 1 ? '1 hour ago' : `${hours} hours ago`
  const days = Math.floor(hours / 24)
  return days === 1 ? '1 day ago' : `${days} days ago`
}

function RefreshIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
      <path d="M3 21v-5h5" />
    </svg>
  )
}

export default function Dashboard() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const courseGridRef = useRef(null)
  const deadlinesLabelRef = useRef(null)
  const [deadlinesMaxHeight, setDeadlinesMaxHeight] = useState(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isReconnecting, setIsReconnecting] = useState(false)

  async function reconnectQuercus() {
    if (isReconnecting) return
    setIsReconnecting(true)
    try {
      await client.delete('/api/courses/quercus-token')
      await queryClient.removeQueries({ queryKey: ['dashboard'] })
      await queryClient.removeQueries({ queryKey: ['courses'] })
      await queryClient.removeQueries({ queryKey: ['course-grades'] })
      await queryClient.invalidateQueries({ queryKey: ['quercus-token-status'] })
      navigate('/onboarding', { replace: true })
    } finally {
      setIsReconnecting(false)
    }
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    staleTime: DASHBOARD_STALE_TIME_MS,
    refetchOnWindowFocus: false,
  })

  const isTokenExpired = error?.response?.status === 424 || data?.auth_error === 'quercus_token_invalid'

  const fetchedAt = data?.fetched_at ?? null
  const termName = useMemo(
    () => (data?.courses ?? []).find((c) => c.term_name)?.term_name ?? '',
    [data],
  )


  const handleRefresh = useCallback(async () => {
    if (isRefreshing) return
    setIsRefreshing(true)
    try {
      const fresh = await fetchDashboard(true)
queryClient.setQueryData(['dashboard'], fresh)
    } finally {
      setIsRefreshing(false)
    }
  }, [queryClient, isRefreshing])

  const deadlines = useMemo(
    () => (data?.courses ?? []).flatMap((course) => course.deadlines ?? []).sort((a, b) => a.due_at.localeCompare(b.due_at)),
    [data],
  )
  const announcements = data?.announcements ?? []


  useEffect(() => {
    if (!courseGridRef.current || !deadlinesLabelRef.current) return undefined

    const updateDeadlinesHeight = () => {
      if (!courseGridRef.current || !deadlinesLabelRef.current) return
      const gridHeight = courseGridRef.current.getBoundingClientRect().height
      const labelHeight = deadlinesLabelRef.current.getBoundingClientRect().height
      const labelMarginBottom = Number.parseFloat(window.getComputedStyle(deadlinesLabelRef.current).marginBottom) || 0
      const nextHeight = Math.max(160, Math.floor(gridHeight - labelHeight - labelMarginBottom))
      setDeadlinesMaxHeight(nextHeight)
    }

    updateDeadlinesHeight()

    const observer = new ResizeObserver(() => {
      updateDeadlinesHeight()
    })

    observer.observe(courseGridRef.current)
    observer.observe(deadlinesLabelRef.current)
    window.addEventListener('resize', updateDeadlinesHeight)

    return () => {
      observer.disconnect()
      window.removeEventListener('resize', updateDeadlinesHeight)
    }
  }, [data])

  return (
    <div className="page dashboard-page">
      <div className="semester-row rise">
        <span className="semester-title">{termName}</span>
        <span className="semester-tag">Active</span>
        <div className="dashboard-freshness">
          {fetchedAt ? (
            <span className="dashboard-age">Updated {formatAge(fetchedAt)}</span>
          ) : null}
          <button
            type="button"
            className={`dashboard-refresh-btn${isRefreshing ? ' refreshing' : ''}`}
            onClick={handleRefresh}
            disabled={isRefreshing}
            aria-label="Refresh dashboard"
          >
            <RefreshIcon />
            {isRefreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="dashboard-loading-card" aria-live="polite">
          <div className="loading-spinner" aria-hidden="true" />
          <div className="dashboard-loading-copy">Loading dashboard…</div>
        </div>
      )}
      {error && !isTokenExpired && <div className="empty-card">Failed to load courses.</div>}
      {error && isTokenExpired && (
        <div className="token-expired-card">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <circle cx="10" cy="10" r="8.5" />
            <path d="M10 6v4.5M10 13.5v.5" strokeLinecap="round" />
          </svg>
          <div className="token-expired-body">
            <div className="token-expired-title">Quercus token expired</div>
            <div className="token-expired-sub">Your token is no longer valid. Reconnect to reload your courses.</div>
          </div>
          <button className="btn-reconnect" type="button" onClick={reconnectQuercus} disabled={isReconnecting}>
            {isReconnecting ? 'Disconnecting…' : 'Reconnect Quercus'}
          </button>
        </div>
      )}

      {!isLoading && (!error || isTokenExpired) && data && (
        <>
          {isTokenExpired && (
            <div className="auth-error-banner" role="alert">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <circle cx="8" cy="8" r="6.5" />
                <path d="M8 5v3.5M8 10.5v.5" strokeLinecap="round" />
              </svg>
              Your Quercus token has expired — grades shown may be outdated.
              <button className="auth-error-reconnect" type="button" onClick={reconnectQuercus} disabled={isReconnecting}>
                {isReconnecting ? 'Disconnecting…' : 'Reconnect'}
              </button>
            </div>
          )}
        <div className="dashboard-main">
          <section className="dashboard-top">
            <section className="course-grid" ref={courseGridRef}>
              {(data?.courses ?? []).map((course) => (
                <CourseCard course={course} key={course.id} />
              ))}
            </section>

            <aside className="dashboard-rail">
              <div className="section-label rise" ref={deadlinesLabelRef}>Upcoming Deadlines</div>
              <DeadlineList deadlines={deadlines} maxHeight={deadlinesMaxHeight} />
            </aside>
          </section>

          <section className="dashboard-announcements">
            <div className="section-label rise">Recent Announcements</div>
            <AnnouncementList announcements={announcements} />
          </section>
        </div>
        </>
      )}

      <footer style={{
        marginTop: 48,
        paddingTop: 16,
        borderTop: '1px solid var(--border)',
        display: 'flex',
        gap: 16,
        justifyContent: 'center',
        flexWrap: 'wrap',
        fontSize: 12,
      }}>
        <Link to="/privacy" className="site-footer-link">Privacy Policy</Link>
        <Link to="/terms" className="site-footer-link">Terms of Use</Link>
        <Link to="/disclaimers" className="site-footer-link">Disclaimers</Link>
      </footer>
    </div>
  )
}
