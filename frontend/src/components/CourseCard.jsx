import { Link } from 'react-router-dom'
import { displayCourseCode } from '../utils/courseCode'

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

export default function CourseCard({ course }) {
  const badge = badgeClass(course.risk_flag)
  const grade = typeof course.current_grade === 'number' ? Math.round(course.current_grade) : '--'

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
      <Link className="btn-view" to={`/courses/${course.id}`}>
        View breakdown
        <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M2 6h8M6 2l4 4-4 4" />
        </svg>
      </Link>
    </article>
  )
}
