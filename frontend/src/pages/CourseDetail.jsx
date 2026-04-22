import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import client from '../api/client'
import { displayCourseCode } from '../utils/courseCode'

const thresholds = [
  ['A+', 90],
  ['A', 85],
  ['A-', 80],
  ['B+', 77],
  ['B', 73],
  ['B-', 70],
  ['C+', 67],
  ['C', 63],
  ['C-', 60],
  ['D+', 57],
  ['D', 53],
  ['F', 0],
]

function toLetter(value) {
  return thresholds.find(([, min]) => value >= min)?.[0] ?? 'F'
}

function displayCourseName(name, courseCode) {
  if (!name) return 'Untitled course'
  if (!courseCode) return name

  const escapedCode = courseCode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const colonPrefix = new RegExp(`^${escapedCode}\\b.*?:\\s*`, 'i')
  const directPrefix = new RegExp(`^${escapedCode}\\b[\\s:-]*`, 'i')

  return name.replace(colonPrefix, '').replace(directPrefix, '').trim() || name
}

export default function CourseDetail() {
  const { id } = useParams()
  const [sliderValues, setSliderValues] = useState({})

  const courseQuery = useQuery({
    queryKey: ['courses'],
    queryFn: async () => {
      const response = await client.get('/api/courses')
      return response.data.courses
    },
  })

  const gradesQuery = useQuery({
    queryKey: ['course-grades', id],
    queryFn: async () => {
      const response = await client.get(`/api/courses/${id}/grades`)
      return response.data
    },
  })

  const course = useMemo(
    () => (courseQuery.data ?? []).find((entry) => String(entry.id) === id),
    [courseQuery.data, id],
  )

  const components = gradesQuery.data?.component_model?.components ?? []
  const projected = useMemo(() => {
    if (!components.length) return null
    return components.reduce((total, component) => {
      const fallback = component.status === 'graded' ? component.pct ?? 0 : 100
      const pct = sliderValues[component.component_key] ?? fallback
      return total + (pct * component.weight) / 100
    }, 0)
  }, [components, sliderValues])

  const remainingComponents = components.filter((component) => component.status === 'ungraded')

  if (courseQuery.isLoading || gradesQuery.isLoading) {
    return <div className="detail-page page"><div className="empty-card">Loading course details…</div></div>
  }

  if (courseQuery.error || gradesQuery.error || !gradesQuery.data) {
    return <div className="detail-page page"><div className="empty-card">Failed to load course details.</div></div>
  }

  const grade = gradesQuery.data.grade
  const currentGrade = grade?.weighted_grade ?? 0
  const letter = grade?.letter ?? 'N/A'
  const gradedWeight = grade?.graded_weight ?? 0

  return (
    <div className="detail-page page">
      <Link className="back-btn" to="/">
        <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M9 2L4 7l5 5" />
        </svg>
        Back to dashboard
      </Link>

      <div className="course-header rise">
        <div className="course-meta">
          <div className="course-code-tag">
            <span className="status-pip" />
            {displayCourseCode(course?.course_code) + ' · Winter 2026'}
          </div>
          <div className="course-name-h">{displayCourseName(course?.name, course?.course_code) || `Course ${id}`}</div>
          <div className="course-sub">Weighted breakdown generated from your current Quercus data.</div>
        </div>
        <div className="grade-hero">
          <div className="grade-big">
            {currentGrade.toFixed(1)}
            <span>%</span>
          </div>
          <div className="grade-letter-hero">{letter}</div>
          <div className="grade-sub">{gradedWeight}% of course graded</div>
        </div>
      </div>

      <div className="divider" />

      <div className="section-label">Grade Breakdown</div>
      <div className="grade-table-wrap rise">
        <table>
          <thead>
            <tr>
              <th>Component</th>
              <th>Weight</th>
              <th>Score</th>
              <th>Contribution</th>
            </tr>
          </thead>
          <tbody>
            {components.map((component) => {
              const isGraded = component.status === 'graded'
              const contribution = isGraded ? ((component.pct ?? 0) * component.weight) / 100 : null
              return (
                <tr key={component.component_key}>
                  <td className="comp-name">
                    {component.name}
                    <span className={`comp-tag ${isGraded ? 'tag-done' : 'tag-remaining'}`}>
                      {isGraded ? 'Graded' : 'Remaining'}
                    </span>
                  </td>
                  <td>{component.weight}%</td>
                  <td className={isGraded ? 'score-cell' : 'score-na'}>{isGraded ? `${component.pct}%` : 'Not yet'}</td>
                  <td className={`contrib-cell ${isGraded ? 'contrib-positive' : ''}`}>
                    {isGraded ? (
                      <div className="mini-bar-wrap">
                        {contribution.toFixed(1)}%
                        <div className="mini-bar">
                          <div className="mini-bar-fill" style={{ width: `${component.pct}%` }} />
                        </div>
                      </div>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr>
              <td className="total-label">Graded so far ({gradedWeight}%)</td>
              <td />
              <td />
              <td className="total-score">{currentGrade.toFixed(1)}%</td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="section-label">What-if Calculator</div>
      <div className="whatif-card rise">
        <div className="whatif-header">
          <div className="whatif-title">
            <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M7 1v6l3 3M13 7A6 6 0 1 1 1 7a6 6 0 0 1 12 0z" />
            </svg>
            Projected Final Grade
          </div>
          <div className="projected-grade">
            <span className="proj-label">If you score these marks:</span>
            <span className="proj-val">{projected?.toFixed(1) ?? currentGrade.toFixed(1)}%</span>
            <span className="proj-letter A">{toLetter(projected ?? currentGrade)}</span>
          </div>
        </div>
        <div className="whatif-body">
          {remainingComponents.length ? (
            remainingComponents.map((component) => {
              const value = sliderValues[component.component_key] ?? 85
              return (
                <div className="slider-row" key={component.component_key}>
                  <div>
                    <div className="slider-name">{component.name}</div>
                    <div className="slider-weight">Weight: {component.weight}%</div>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={value}
                    onChange={(event) =>
                      setSliderValues((current) => ({
                        ...current,
                        [component.component_key]: Number(event.target.value),
                      }))
                    }
                    style={{
                      background: `linear-gradient(to right, oklch(68% 0.16 240) ${value}%, oklch(19% 0.022 260) ${value}%)`,
                    }}
                  />
                  <div className="slider-val">{value}%</div>
                </div>
              )
            })
          ) : (
            <div className="empty-inline">No remaining weighted components available for projection.</div>
          )}
        </div>
      </div>

      <p className="disclaimer">
        Projected grades are estimates based on available data and may not reflect official university records. Verify grades on ACORN and consult your instructor for authoritative information.
      </p>
    </div>
  )
}
