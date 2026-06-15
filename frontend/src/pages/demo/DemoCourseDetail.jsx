import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useDemoData } from '../../context/DemoDataContext'
import { displayCourseCode } from '../../utils/courseCode'

const thresholds = [
  ['A+', 90], ['A', 85], ['A-', 80], ['B+', 77], ['B', 73], ['B-', 70],
  ['C+', 67], ['C', 63], ['C-', 60], ['D+', 57], ['D', 53], ['F', 0],
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

export default function DemoCourseDetail() {
  const { courseId } = useParams()
  const { courses, courseGrades } = useDemoData()
  const [sliderValues, setSliderValues] = useState({})

  const course = courses.find((c) => c.id === courseId)
  const gradesData = courseGrades[courseId]

  if (!course || !gradesData) {
    return <div className="detail-page page"><div className="empty-card">Course not found.</div></div>
  }

  const components = gradesData.component_model.components
  const assignmentsByComponent = gradesData.component_model.assignments_by_component

  const gradedComponents = useMemo(
    () => components
      .filter((c) => c.status === 'graded')
      .map((c) => ({ ...c, assignmentRows: assignmentsByComponent[c.component_key] ?? [] })),
    [components, assignmentsByComponent],
  )

  const remainingComponents = components.filter((c) => c.status === 'ungraded')

  const projected = useMemo(() => {
    return components.reduce((total, component) => {
      const fallback = component.status === 'graded' ? component.pct ?? 0 : 100
      const pct = sliderValues[component.component_key] ?? fallback
      return total + (pct * component.weight) / 100
    }, 0)
  }, [components, sliderValues])

  const projectedLetter = toLetter(projected)

  return (
    <div className="detail-page page">
      <Link className="back-btn" to="/demo/dashboard">
        <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M9 2L4 7l5 5" />
        </svg>
        Back to dashboard
      </Link>

      <div className="course-header rise">
        <div className="course-meta">
          <div className="course-code-tag">
            <span className="status-pip" />
            {displayCourseCode(course.course_code) + ' · Fall 2025'}
          </div>
          <div className="course-name-h">{displayCourseName(course.name, course.course_code)}</div>
          <div className="course-sub">Weighted breakdown generated from sample data.</div>
        </div>
        <div className="grade-hero">
          <div className="grade-big">
            {projected.toFixed(1)}
            <span>%</span>
          </div>
          <div className="grade-letter-hero">{projectedLetter}</div>
        </div>
      </div>

      <div className="section-label">Graded Components</div>
      <div className="graded-with-rail">
        <div className="grade-toggle-rail">
          <div className="grade-toggle-rail-head" />
          {gradedComponents.map((row) => (
            <div className="grade-toggle-rail-row" key={row.component_key} />
          ))}
        </div>

        <div className="grade-table-wrap rise">
          <table>
            <thead>
              <tr>
                <th>Component</th>
                <th>Weight</th>
                <th>Score</th>
                <th className="score-action-head" aria-label="Edit action" />
              </tr>
            </thead>
            <tbody>
              {gradedComponents.map((row) => (
                <tr key={row.component_key}>
                  <td className="comp-name">
                    <div className="comp-name-main">
                      {row.name}
                      <span className="comp-tag tag-done">Graded</span>
                    </div>
                    {row.assignmentRows.length > 1 && (
                      <div className="comp-subrows">
                        {row.assignmentRows.map((a) => (
                          <div className="comp-subrow" key={a.assignment_id}>
                            {a.name} · {a.earned}/{a.possible} pts ({a.pct}%)
                          </div>
                        ))}
                      </div>
                    )}
                  </td>
                  <td>{row.weight}%</td>
                  <td className="score-cell">
                    <div className="score-control">
                      <div className="score-field-shell">
                        <span className="score-chip">{row.pct}%</span>
                      </div>
                    </div>
                  </td>
                  <td className="score-action-cell" />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="section-label">What-if Calculator</div>
      <div className="whatif-outer-wrap">
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
              <span className="proj-val">{projected.toFixed(1)}%</span>
              <span className="proj-letter A">{projectedLetter}</span>
            </div>
          </div>
          <div className="whatif-body">
            {remainingComponents.length ? (
              remainingComponents.map((component) => {
                const value = sliderValues[component.component_key] ?? 100
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
                      onChange={(e) =>
                        setSliderValues((cur) => ({ ...cur, [component.component_key]: Number(e.target.value) }))
                      }
                      style={{
                        background: `linear-gradient(to right, var(--accent) ${value}%, var(--surface3) ${value}%)`,
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
      </div>

      <p className="disclaimer">
        Projected grades are estimates based on sample data. Sign in to see calculations based on your real Quercus grades.
      </p>
    </div>
  )
}
