import { useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import client from '../api/client'
import { displayCourseCode } from '../utils/courseCode'

const COURSE_DETAIL_STALE_TIME_MS = 5 * 60 * 1000

function progressClass(pct) {
  if (pct >= 80) return 'a-range'
  if (pct >= 70) return 'b-range'
  if (pct >= 60) return 'c-range'
  return 'd-range'
}

function displayCourseName(name, courseCode) {
  if (!name) return 'Untitled course'
  if (!courseCode) return name

  const escapedCode = courseCode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const colonPrefix = new RegExp(`^${escapedCode}\\b.*?:\\s*`, 'i')
  const directPrefix = new RegExp(`^${escapedCode}\\b[\\s:-]*`, 'i')

  return name.replace(colonPrefix, '').replace(directPrefix, '').trim() || name
}

export default function CourseCard({ course }) {
  const queryClient = useQueryClient()
  const gradeValue = typeof course.display_grade === 'number' ? course.display_grade : course.current_grade
  const grade = typeof gradeValue === 'number' ? Math.round(gradeValue) : '--'
  const noBreakdown = course.risk_flag === 'No breakdown'
  const fillClass = typeof grade === 'number' ? progressClass(grade) : 'track'

  function prefetchCourseDetail() {
    queryClient.prefetchQuery({
      queryKey: ['course-grades', String(course.id)],
      queryFn: async () => {
        const response = await client.get(`/api/courses/${course.id}/grades`)
        return response.data
      },
      staleTime: COURSE_DETAIL_STALE_TIME_MS,
    })
  }

  return (
    <article className="course-card rise">
      <div className="card-top">
        <div>
          <div className="course-code">{displayCourseCode(course.course_code)}</div>
          <div className="course-name">{displayCourseName(course.name, course.course_code)}</div>
        </div>
      </div>
      <div className="grade-row">
        <span className="grade-pct">{grade}</span>
        <span className="grade-letter">% · {course.letter_grade || 'N/A'}</span>
      </div>
      <div className="progress-wrap">
        <div className={`progress-fill fill-${fillClass}`} style={{ width: `${Math.max(0, Math.min(100, grade || 0))}%` }} />
      </div>
      {noBreakdown ? (
        <span className="btn-view btn-view-disabled" aria-disabled="true">
          View breakdown
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M2 6h8M6 2l4 4-4 4" />
          </svg>
        </span>
      ) : (
        <Link
          className="btn-view"
          to={`/courses/${course.id}`}
          onMouseEnter={prefetchCourseDetail}
          onFocus={prefetchCourseDetail}
          onTouchStart={prefetchCourseDetail}
        >
          View breakdown
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M2 6h8M6 2l4 4-4 4" />
          </svg>
        </Link>
      )}
    </article>
  )
}
