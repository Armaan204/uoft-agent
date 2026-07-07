import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
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
  const [confirmDelete, setConfirmDelete] = useState(false)
  const isManual = course.source === 'manual'
  const gradeValue = typeof course.display_grade === 'number' ? course.display_grade : course.current_grade
  const grade = typeof gradeValue === 'number' ? Math.round(gradeValue) : '--'
  const noBreakdown = course.risk_flag === 'No breakdown'
  const fillClass = typeof grade === 'number' ? progressClass(grade) : 'track'

  const deleteMutation = useMutation({
    mutationFn: () => client.delete(`/api/manual-courses/${course.id}`),
    onMutate: () => {
      queryClient.setQueryData(['dashboard'], (old) => {
        if (!old) return old
        return { ...old, courses: (old.courses || []).filter((c) => c.id !== course.id) }
      })
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
  })

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
    <article className={`course-card rise${isManual ? ' manual-course-card' : ''}`}>
      <div className="card-top">
        <div>
          <div className="course-code">
            {displayCourseCode(course.course_code)}
            {isManual && <span className="manual-badge">Manual</span>}
          </div>
          <div className="course-name">{displayCourseName(course.name, course.course_code)}</div>
        </div>
        {isManual && (
          confirmDelete ? (
            <div className="card-delete-confirm">
              <button type="button" className="card-delete-yes" onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending}>
                {deleteMutation.isPending ? '…' : 'Delete'}
              </button>
              <button type="button" className="card-delete-no" onClick={() => setConfirmDelete(false)}>Cancel</button>
            </div>
          ) : (
            <button type="button" className="card-delete-btn" onClick={() => setConfirmDelete(true)} aria-label="Delete course">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" width="15" height="15">
                <path d="M2 4h12M5.5 4V2.5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1V4M6.5 7v4M9.5 7v4" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M3.5 4l.5 9a1.5 1.5 0 0 0 1.5 1.5h5A1.5 1.5 0 0 0 12 13l.5-9" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          )
        )}
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
