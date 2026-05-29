import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import client from '../api/client'
import { displayCourseCode } from '../utils/courseCode'

const DASHBOARD_STALE_TIME_MS = 5 * 60 * 1000
const COURSE_DATA_STALE_TIME_MS = 5 * 60 * 1000
const COURSE_DATA_GC_TIME_MS = 30 * 60 * 1000

const EMPTY_COMPONENTS = []
const EMPTY_ASSIGNMENTS_BY_COMPONENT = {}

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

function parseScoreValue(rawValue) {
  const parsed = Number.parseFloat(rawValue)
  if (!Number.isFinite(parsed)) return null
  return Math.max(0, Math.min(100, parsed))
}

export default function CourseDetail() {
  const { id } = useParams()
  const [sliderValues, setSliderValues] = useState({})
  const [editingKey, setEditingKey] = useState(null)
  const [draftScores, setDraftScores] = useState({})

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

  const termName = dashboardCourse?.term_name ?? queryClient.getQueryData(['dashboard'])?.term_name ?? ''

  const course = useMemo(
    () => (courseQuery.data ?? []).find((entry) => String(entry.id) === id) ?? dashboardCourse,
    [courseQuery.data, dashboardCourse, id],
  )

  const components = gradesQuery.data?.component_model?.components ?? EMPTY_COMPONENTS
  const assignmentsByComponent = gradesQuery.data?.component_model?.assignments_by_component ?? EMPTY_ASSIGNMENTS_BY_COMPONENT
  const liveComponents = gradesQuery.data?.live_components ?? []
  const liveStatusByKey = useMemo(() => {
    const map = {}
    liveComponents.forEach((c) => { if (c.component_key) map[c.component_key] = c.status })
    return map
  }, [liveComponents])

  const gradedComponents = useMemo(
    () =>
      components
        .filter((component) => component.status === 'graded')
        .map((component) => ({
          ...component,
          assignmentRows: (assignmentsByComponent[component.component_key] ?? []).filter((row) => row.status === 'graded'),
        })),
    [assignmentsByComponent, components],
  )

  const projected = useMemo(() => {
    if (!components.length) return null
    return components.reduce((total, component) => {
      const fallback = component.status === 'graded' ? component.pct ?? 0 : 100
      const pct = sliderValues[component.component_key] ?? fallback
      return total + (pct * component.weight) / 100
    }, 0)
  }, [components, sliderValues])

  const remainingComponents = components.filter((component) => component.status === 'ungraded')

  const gradeRailRef = useRef(null)
  const gradeTableRef = useRef(null)
  const whatifRailRef = useRef(null)
  const whatifCardRef = useRef(null)

  useLayoutEffect(() => {
    const rail = gradeRailRef.current
    const table = gradeTableRef.current
    if (!rail || !table) return
    const thead = table.querySelector('thead')
    const headSlot = rail.querySelector('.grade-toggle-rail-head')
    if (thead && headSlot) headSlot.style.height = `${thead.offsetHeight}px`
    const rows = table.querySelectorAll('tbody tr')
    const slots = rail.querySelectorAll('.grade-toggle-rail-row')
    rows.forEach((row, i) => { if (slots[i]) slots[i].style.minHeight = `${row.offsetHeight}px` })
  }, [gradedComponents])

  useLayoutEffect(() => {
    const rail = whatifRailRef.current
    const card = whatifCardRef.current
    if (!rail || !card) return
    const header = card.querySelector('.whatif-header')
    const headSlot = rail.querySelector('.whatif-toggle-rail-head')
    if (header && headSlot) headSlot.style.height = `${header.offsetHeight}px`
    const rows = card.querySelectorAll('.slider-row')
    const slots = rail.querySelectorAll('.whatif-toggle-rail-row')
    rows.forEach((row, i) => { if (slots[i]) slots[i].style.minHeight = `${row.offsetHeight}px` })
  }, [remainingComponents])

  const saveOverrideMutation = useMutation({
    mutationFn: async (override) => {
      const response = await client.post(`/api/courses/${id}/grade-overrides`, {
        overrides: [override],
      })
      return response.data
    },
    onSuccess: async (data) => {
      queryClient.setQueryData(['course-grades', id], data)
      await queryClient.invalidateQueries({ queryKey: ['course-grades', id] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      setEditingKey(null)
    },
  })

  const markGradedMutation = useMutation({
    mutationFn: async ({ componentKey, value }) => {
      const response = await client.post(`/api/courses/${id}/grade-overrides`, {
        overrides: [{ component_key: componentKey, manual_score: value, manual_possible: 100 }],
      })
      return response.data
    },
    onMutate: async ({ componentKey, value }) => {
      await queryClient.cancelQueries({ queryKey: ['course-grades', id] })
      const previousData = queryClient.getQueryData(['course-grades', id])
      queryClient.setQueryData(['course-grades', id], (old) => {
        if (!old) return old
        const newComponents = old.component_model.components.map((c) =>
          c.component_key !== componentKey ? c : {
            ...c, status: 'graded', pct: value, earned: value, possible: 100,
            is_manual: true, manual_score: value, manual_possible: 100,
          }
        )
        return { ...old, component_model: { ...old.component_model, components: newComponents } }
      })
      return { previousData }
    },
    onError: (_err, _componentKey, context) => {
      if (context?.previousData) queryClient.setQueryData(['course-grades', id], context.previousData)
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['course-grades', id], data)
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  const deleteOverrideMutation = useMutation({
    mutationFn: async (componentKey) => {
      const response = await client.delete(`/api/courses/${id}/grade-overrides/${encodeURIComponent(componentKey)}`)
      return response.data
    },
    onMutate: async (componentKey) => {
      await queryClient.cancelQueries({ queryKey: ['course-grades', id] })
      const previousData = queryClient.getQueryData(['course-grades', id])
      queryClient.setQueryData(['course-grades', id], (old) => {
        if (!old) return old
        const liveComp = (old.live_components ?? []).find((c) => c.component_key === componentKey)
        const newComponents = old.component_model.components.map((c) => {
          if (c.component_key !== componentKey) return c
          return liveComp ? { ...liveComp } : { ...c, status: 'ungraded', pct: null, earned: null, is_manual: false, manual_score: null, manual_possible: null }
        })
        return { ...old, component_model: { ...old.component_model, components: newComponents } }
      })
      return { previousData }
    },
    onError: (_err, _componentKey, context) => {
      if (context?.previousData) queryClient.setQueryData(['course-grades', id], context.previousData)
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['course-grades', id], data)
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

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

  useEffect(() => {
    if (!gradedComponents.length) {
      setDraftScores({})
      setEditingKey(null)
      return
    }

    setDraftScores((current) => {
      const next = {}
      gradedComponents.forEach((component) => {
        next[component.component_key] = current[component.component_key] ?? String(component.pct ?? '')
      })
      return next
    })
  }, [gradedComponents])

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

  function startEditing(component) {
    setDraftScores((current) => ({
      ...current,
      [component.component_key]: String(component.pct ?? ''),
    }))
    setEditingKey(component.component_key)
  }

  function cancelEditing(component) {
    setDraftScores((current) => ({
      ...current,
      [component.component_key]: String(component.pct ?? ''),
    }))
    setEditingKey((current) => (current === component.component_key ? null : current))
  }

  function saveEditing(component) {
    const nextPct = parseScoreValue(draftScores[component.component_key])
    if (nextPct === null || typeof component.pct !== 'number') return
    if (Math.abs(nextPct - component.pct) <= 0.01) {
      setEditingKey(null)
      return
    }

    const possible = Number(component.possible)
    if (!Number.isFinite(possible) || possible <= 0) return

    saveOverrideMutation.mutate({
      component_key: component.component_key,
      manual_score: Number(((possible * nextPct) / 100).toFixed(2)),
      manual_possible: possible,
    })
  }

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
            {displayCourseCode(course?.course_code) + (termName ? ` · ${termName}` : '')}
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

      <div className="section-label">Graded Components</div>
      <div className="graded-with-rail">
        {/* Toggle buttons live outside the table card in this left rail */}
        <div className="grade-toggle-rail" ref={gradeRailRef}>
          <div className="grade-toggle-rail-head" />
          {gradedComponents.map((row) => {
            const isEditing = editingKey === row.component_key
            const isSaving = saveOverrideMutation.isPending && saveOverrideMutation.variables?.component_key === row.component_key
            const isManualFromUngraded = row.is_manual && liveStatusByKey[row.component_key] === 'ungraded'
            const isDeleting = deleteOverrideMutation.isPending && deleteOverrideMutation.variables === row.component_key
            const isPendingBtnBusy = isDeleting || (markGradedMutation.isPending && markGradedMutation.variables?.componentKey === row.component_key)
            return (
              <div className="grade-toggle-rail-row" key={row.component_key}>
                {isManualFromUngraded && !isEditing && (
                  <button
                    className={`grade-toggle-btn${isPendingBtnBusy ? ' visible' : ''}`}
                    type="button"
                    onClick={() => {
                      setSliderValues((current) => ({ ...current, [row.component_key]: row.pct ?? 100 }))
                      deleteOverrideMutation.mutate(row.component_key)
                    }}
                    disabled={isPendingBtnBusy || isSaving}
                  >
                    {isPendingBtnBusy ? (
                      <><div className="grade-toggle-spinner" />{"Move to\npending"}</>
                    ) : (
                      <>
                        <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="M6 2v8M2 6l4 4 4-4" />
                        </svg>
                        {"Move to\npending"}
                      </>
                    )}
                  </button>
                )}
              </div>
            )
          })}
        </div>

        <div className="grade-table-wrap rise" ref={gradeTableRef}>
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
              {gradedComponents.map((row) => {
                const isEditing = editingKey === row.component_key
                const isSaving = saveOverrideMutation.isPending && saveOverrideMutation.variables?.component_key === row.component_key
                const isManualFromUngraded = row.is_manual && liveStatusByKey[row.component_key] === 'ungraded'
                return (
                  <tr className={isEditing ? 'grade-row-editing' : ''} key={row.component_key}>
                    <td className="comp-name">
                      <div className="comp-name-main">
                        {row.name}
                        <span className="comp-tag tag-done">Graded</span>
                        {isManualFromUngraded && <span className="comp-tag tag-manual">Manual</span>}
                      </div>
                      {row.assignmentRows.length > 1 ? (
                        <div className="comp-subrows">
                          {row.assignmentRows.map((assignment) => (
                            <div className="comp-subrow" key={assignment.assignment_id}>
                              {assignment.name || row.name} · {assignment.earned}/{assignment.possible} pts
                              {typeof assignment.pct === 'number' ? ` (${assignment.pct}%)` : ''}
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </td>
                    <td>{row.weight.toFixed(2).replace(/\.00$/, '')}%</td>
                    <td className="score-cell">
                      <div className={`score-control ${isEditing ? 'editing' : ''}`}>
                        <div className="score-field-shell">
                          {isEditing ? (
                            <>
                              <input
                                className="score-inline-input"
                                type="number"
                                min="0"
                                max="100"
                                step="0.1"
                                value={draftScores[row.component_key] ?? ''}
                                disabled={isSaving}
                                onChange={(event) =>
                                  setDraftScores((current) => ({
                                    ...current,
                                    [row.component_key]: event.target.value,
                                  }))
                                }
                              />
                              <span className="score-inline-suffix">%</span>
                            </>
                          ) : (
                            <span className="score-chip">{row.pct}%</span>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="score-action-cell">
                      <div className="score-actions">
                        {isEditing ? (
                          <>
                            <button
                              className="score-action-btn save"
                              type="button"
                              onClick={() => saveEditing(row)}
                              disabled={isSaving}
                              aria-label={`Save adjusted score for ${row.name}`}
                            >
                              {isSaving ? '...' : '✓'}
                            </button>
                            <button
                              className="score-action-btn cancel"
                              type="button"
                              onClick={() => cancelEditing(row)}
                              disabled={isSaving}
                              aria-label={`Cancel editing score for ${row.name}`}
                            >
                              ×
                            </button>
                          </>
                        ) : (
                          <button
                            className="score-action-btn edit"
                            type="button"
                            onClick={() => startEditing(row)}
                            aria-label={`Edit score for ${row.name}`}
                          >
                            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                              <path d="M11.8 2.2a1.55 1.55 0 0 1 2.2 2.2l-7.6 7.6-3.4.5.5-3.4 7.6-7.6Z" />
                              <path d="m10.6 3.4 2 2" />
                            </svg>
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
      {saveOverrideMutation.error || markGradedMutation.error || deleteOverrideMutation.error ? (
        <div className="onboarding-error">
          {(saveOverrideMutation.error || markGradedMutation.error || deleteOverrideMutation.error)?.response?.data?.detail || 'Could not save grade change.'}
        </div>
      ) : null}

      <div className="section-label">What-if Calculator</div>
      <div className="whatif-outer-wrap">
        {/* Toggle buttons live outside the card in this left rail */}
        {remainingComponents.length ? (
          <div className="whatif-toggle-rail" ref={whatifRailRef}>
            <div className="whatif-toggle-rail-head" />
            {remainingComponents.map((component) => {
              const isMarking = markGradedMutation.isPending && markGradedMutation.variables?.componentKey === component.component_key
              const isGradedBtnBusy = isMarking || (deleteOverrideMutation.isPending && deleteOverrideMutation.variables === component.component_key)
              return (
                <div className="whatif-toggle-rail-row" key={component.component_key}>
                  <button
                    className={`grade-toggle-btn${isGradedBtnBusy ? ' visible' : ''}`}
                    type="button"
                    onClick={() => markGradedMutation.mutate({ componentKey: component.component_key, value: sliderValues[component.component_key] ?? 100 })}
                    disabled={isGradedBtnBusy}
                  >
                    {isGradedBtnBusy ? (
                      <><div className="grade-toggle-spinner" />{"Mark as\ngraded"}</>
                    ) : (
                      <>
                        <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="M6 10V2M2 6l4-4 4 4" />
                        </svg>
                        {"Mark as\ngraded"}
                      </>
                    )}
                  </button>
                </div>
              )
            })}
          </div>
        ) : null}

        <div className="whatif-card rise" ref={whatifCardRef}>
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
      </div>

      <p className="disclaimer">
        Projected grades are estimates based on available data and may not reflect official university records. Verify grades on ACORN and consult your instructor for authoritative information.
      </p>
    </div>
  )
}
