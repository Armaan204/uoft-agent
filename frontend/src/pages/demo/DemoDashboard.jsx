import { useMemo, useRef, useState, useEffect } from 'react'
import { Link } from 'react-router-dom'

import { useDemoData } from '../../context/DemoDataContext'
import { displayCourseCode } from '../../utils/courseCode'
import DeadlineList from '../../components/DeadlineList'

function badgeClass(flag) {
  if (flag === 'Safe') return 'safe'
  if (flag === 'At risk') return 'risk'
  return 'track'
}

function displayCourseName(name, courseCode) {
  if (!name) return 'Untitled course'
  if (!courseCode) return name
  const escapedCode = courseCode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const colonPrefix = new RegExp(`^${escapedCode}\\b.*?:\\s*`, 'i')
  const directPrefix = new RegExp(`^${escapedCode}\\b[\\s:-]*`, 'i')
  return name.replace(colonPrefix, '').replace(directPrefix, '').trim() || name
}

function DemoCourseCard({ course }) {
  const badge = badgeClass(course.risk_flag)
  const grade = typeof course.display_grade === 'number' ? Math.round(course.display_grade) : '--'

  return (
    <article className="course-card rise">
      <div className="card-top">
        <div>
          <div className="course-code">{displayCourseCode(course.course_code)}</div>
          <div className="course-name">{displayCourseName(course.name, course.course_code)}</div>
        </div>
        <span className={`badge ${badge}`}>{course.risk_flag}</span>
      </div>
      <div className="grade-row">
        <span className="grade-pct">{grade}</span>
        <span className="grade-letter">% · {course.letter_grade || 'N/A'}</span>
      </div>
      <div className="progress-wrap">
        <div className={`progress-fill fill-${badge}`} style={{ width: `${Math.max(0, Math.min(100, grade || 0))}%` }} />
      </div>
      <Link className="btn-view" to={`/demo/courses/${course.id}`}>
        View breakdown
        <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M2 6h8M6 2l4 4-4 4" />
        </svg>
      </Link>
    </article>
  )
}

function formatPosted(postedAt) {
  if (!postedAt) return 'Recently posted'
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(new Date(postedAt))
}

export default function DemoDashboard() {
  const { courses, announcements } = useDemoData()
  const courseGridRef = useRef(null)
  const deadlinesLabelRef = useRef(null)
  const [deadlinesMaxHeight, setDeadlinesMaxHeight] = useState(null)

  const deadlines = useMemo(
    () => courses.flatMap((c) => c.deadlines ?? []).sort((a, b) => a.due_at.localeCompare(b.due_at)),
    [courses],
  )

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
    const observer = new ResizeObserver(() => updateDeadlinesHeight())
    observer.observe(courseGridRef.current)
    observer.observe(deadlinesLabelRef.current)
    window.addEventListener('resize', updateDeadlinesHeight)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', updateDeadlinesHeight)
    }
  }, [])

  return (
    <div className="page dashboard-page">
      <div className="semester-row rise">
        <span className="semester-title">Fall 2025</span>
        <span className="semester-tag">Active</span>
      </div>

      <div className="dashboard-main">
        <section className="dashboard-top">
          <section className="course-grid" ref={courseGridRef}>
            {courses.map((course) => (
              <DemoCourseCard course={course} key={course.id} />
            ))}
          </section>

          <aside className="dashboard-rail">
            <div className="section-label rise" ref={deadlinesLabelRef}>Upcoming Deadlines</div>
            <DeadlineList deadlines={deadlines} maxHeight={deadlinesMaxHeight} />
          </aside>
        </section>

        <section className="dashboard-announcements">
          <div className="section-label rise">Recent Announcements</div>
          <div className="deadlines announcements rise">
            {announcements.map((a) => (
              <div className="announcement-item" key={`${a.course_id}-${a.title}`}>
                <div className="announcement-code">{displayCourseCode(a.course_code)}</div>
                <div className="announcement-body">
                  <div className="announcement-title">{a.title}</div>
                  <div className="announcement-preview">{a.preview}</div>
                </div>
                <div className="announcement-date">{formatPosted(a.posted_at)}</div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
