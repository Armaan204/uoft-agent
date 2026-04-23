import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import client from '../api/client'
import AnnouncementList from '../components/AnnouncementList'
import CourseCard from '../components/CourseCard'
import DeadlineList from '../components/DeadlineList'

const DASHBOARD_STALE_TIME_MS = 5 * 60 * 1000
const DASHBOARD_GC_TIME_MS = 30 * 60 * 1000

async function fetchDashboard() {
  const response = await client.get('/api/courses/dashboard')
  return response.data
}

export default function Dashboard() {
  const courseGridRef = useRef(null)
  const deadlinesLabelRef = useRef(null)
  const [deadlinesMaxHeight, setDeadlinesMaxHeight] = useState(null)

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    staleTime: DASHBOARD_STALE_TIME_MS,
    gcTime: DASHBOARD_GC_TIME_MS,
    refetchOnWindowFocus: false,
  })

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
        {isFetching && !isLoading ? (
          <span className="dashboard-refresh-indicator" aria-live="polite">
            <span className="loading-spinner small" aria-hidden="true" />
            Refreshing
          </span>
        ) : null}
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
