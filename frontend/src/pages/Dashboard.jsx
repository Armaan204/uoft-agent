import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M1.5 7a5.5 5.5 0 1 0 1.1-3.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M1.5 2.5v4h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function Dashboard() {
  const queryClient = useQueryClient()
  const courseGridRef = useRef(null)
  const deadlinesLabelRef = useRef(null)
  const [deadlinesMaxHeight, setDeadlinesMaxHeight] = useState(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    staleTime: DASHBOARD_STALE_TIME_MS,
    refetchOnWindowFocus: false,
  })

  const fetchedAt = data?.fetched_at ?? null

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
      const gridHeight = courseGridRef.current?.getBoundingClientRect().height ?? 0
      const labelHeight = deadlinesLabelRef.current?.getBoundingClientRect().height ?? 0
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
        <span className="semester-title">Winter 2026</span>
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
      {error && <div className="empty-card">Failed to load courses.</div>}

      {!isLoading && !error && (
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
      )}
    </div>
  )
}
