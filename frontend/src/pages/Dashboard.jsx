import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import client from '../api/client'
import AnnouncementList from '../components/AnnouncementList'
import CourseCard from '../components/CourseCard'
import DeadlineList from '../components/DeadlineList'

export default function Dashboard() {
  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const response = await client.get('/api/courses/dashboard')
      return response.data
    },
  })

  const deadlines = useMemo(
    () => (data?.courses ?? []).flatMap((course) => course.deadlines ?? []).sort((a, b) => a.due_at.localeCompare(b.due_at)),
    [data],
  )
  const announcements = data?.announcements ?? []

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
            <section className="course-grid">
              {(data?.courses ?? []).map((course) => (
                <CourseCard course={course} key={course.id} />
              ))}
            </section>

            <aside className="dashboard-rail">
              <div className="section-label rise">Upcoming Deadlines</div>
              <DeadlineList deadlines={deadlines} />
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
