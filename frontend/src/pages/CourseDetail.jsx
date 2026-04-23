import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import client from '../api/client'
import { displayCourseCode } from '../utils/courseCode'

const DASHBOARD_STALE_TIME_MS = 5 * 60 * 1000
const COURSE_DATA_STALE_TIME_MS = 5 * 60 * 1000
const COURSE_DATA_GC_TIME_MS = 30 * 60 * 1000

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
  const queryClient = useQueryClient()

  const courseQuery = useQuery({
    queryKey: ['courses'],
    queryFn: async () => {
      const response = await client.get('/api/courses')
      return response.data.courses
    },
    staleTime: COURSE_DATA_STALE_TIME_MS,
    gcTime: COURSE_DATA_GC_TIME_MS,
    refetchOnWindowFocus: false,
  })

  const gradesQuery = useQuery({
    queryKey: ['course-grades', id],
    queryFn: async () => {
      const response = await client.get(`/api/courses/${id}/grades`)
      return response.data
    },
    staleTime: COURSE_DATA_STALE_TIME_MS,
    gcTime: COURSE_DATA_GC_TIME_MS,
    refetchOnWindowFocus: false,
  })

  const dashboardCourse = useMemo(
    () => (queryClient.getQueryData(['dashboard'])?.courses ?? []).find((entry) => String(entry.id) === id),
    [id, queryClient],
  )

  const course = useMemo(
    () => (courseQuery.data ?? []).find((entry) => String(entry.id) === id) ?? dashboardCourse,
    [courseQuery.data, dashboardCourse, id],
  )

  const components = gradesQuery.data?.component_model?.components ?? []
  const assignmentsByComponent = gradesQuery.data?.component_model?.assignments_by_component ?? {}
  const gradedComponents = components.filter((component) => component.status === 'graded')
  const gradeBreakdownRows = useMemo(() => {
    return gradedComponents.flatMap((component) => {
      const assignmentRows = (assignmentsByComponent[component.component_key] ?? []).filter(
        (row) => row.status === 'graded',
      )

      if (!assignmentRows.length) {
        return [{
          key: component.component_key,
          name: component.name,
          weight: component.weight,
          pct: component.pct,
        }]
      }

      const perAssignmentWeight = component.weight / assignmentRows.length

      return assignmentRows.map((row) => ({
        key: `${component.component_key}:${row.assignment_id}`,
        name: row.name || component.name,
        weight: perAssignmentWeight,
        pct: row.pct,
      }))
    })
  }, [assignmentsByComponent, gradedComponents])
  const projected = useMemo(() => {
    if (!components.length) return null
    return components.reduce((total, component) => {
      const fallback = component.status === 'graded' ? component.pct ?? 0 : 100
      const pct = sliderValues[component.component_key] ?? fallback
      return total + (pct * component.weight) / 100
    }, 0)
  }, [components, sliderValues])

  const remainingComponents = components.filter((component) => component.status === 'ungraded')

  useEffect(() => {
    queryClient.prefetchQuery({
      queryKey: ['dashboard'],
      queryFn: async () => {
        const response = await client.get('/api/courses/dashboard')
        return response.data
      },
      staleTime: DASHBOARD_STALE_TIME_MS,
    })
  }, [queryClient])

  if (gradesQuery.isLoading) {
    return (
      <div className="detail-page page">
        <div className="dashboard-loading-card" aria-live="polite">
          <div className="loading-spinner" aria-hidden="true" />
          <div className="dashboard-loading-copy">Loading course details…</div>
        </div>
      </div>
    )
  }

  if (gradesQuery.error || !gradesQuery.data) {
    return <div className="detail-page page"><div className="empty-card">Failed to load course details.</div></div>
  }

  const grade = gradesQuery.data.grade
  const currentGrade = grade?.weighted_grade ?? 0
  const projectedDefault = projected ?? currentGrade
  const projectedLetter = toLetter(projectedDefault)

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
            {projectedDefault.toFixed(1)}
            <span>%</span>
          </div>
          <div className="grade-letter-hero">{projectedLetter}</div>
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
            </tr>
          </thead>
          <tbody>
            {gradeBreakdownRows.map((row) => {
              return (
                <tr key={row.key}>
                  <td className="comp-name">
                    {row.name}
                    <span className="comp-tag tag-done">Graded</span>
                  </td>
                  <td>{row.weight.toFixed(2).replace(/\.00$/, '')}%</td>
                  <td className="score-cell">{row.pct}%</td>
                </tr>
              )
            })}
          </tbody>
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
            <span className="proj-val">{projectedDefault.toFixed(1)}%</span>
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
