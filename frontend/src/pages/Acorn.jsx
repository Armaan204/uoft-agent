import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import client from '../api/client'

const IMPORT_CODE_KEY = 'uoft-agent-acorn-import-code'
const ACORN_EXTENSION_URL =
  'https://chromewebstore.google.com/detail/akchfgkjeenfkmcommdpnimgkbnclgfa?utm_source=item-share-cb'

const UNEARNED_GRADES = new Set(['IPR', 'NGA'])
const TERM_ORDER = {
  winter: 0,
  spring: 1,
  summer: 2,
  fall: 3,
}

function generateImportCode() {
  const bytes = new Uint8Array(4)
  window.crypto.getRandomValues(bytes)
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('').toUpperCase()
}

function ensureImportCode() {
  const existing = window.localStorage.getItem(IMPORT_CODE_KEY)
  if (existing) return existing
  const next = generateImportCode()
  window.localStorage.setItem(IMPORT_CODE_KEY, next)
  return next
}

function resetImportCode() {
  const next = generateImportCode()
  window.localStorage.setItem(IMPORT_CODE_KEY, next)
  return next
}

function formatTimestamp(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function termSortKey(term) {
  const normalized = String(term || '').trim()
  const match = normalized.match(/(20\d{2}).*?(winter|spring|summer|fall)/i)
  if (match) {
    return [Number(match[1]), TERM_ORDER[match[2].toLowerCase()] ?? 9]
  }
  const trailingYear = normalized.match(/(20\d{2})/)
  if (trailingYear) {
    return [Number(trailingYear[1]), 9]
  }
  return [0, 9]
}

function sortTerms(a, b) {
  const [yearA, seasonA] = termSortKey(a?.term)
  const [yearB, seasonB] = termSortKey(b?.term)
  if (yearA !== yearB) return yearA - yearB
  return seasonA - seasonB
}

function buildTrendChart(terms, key) {
  const filtered = (terms ?? []).filter((term) => typeof term?.[key] === 'number').sort(sortTerms)
  if (!filtered.length) {
    return {
      points: [],
      ticks: [],
      areaPath: '',
      linePath: '',
      domain: { min: 0, max: 4 },
      chart: { left: 56, right: 704, top: 30, bottom: 208, width: 648, height: 178 },
    }
  }

  const chart = { left: 56, right: 704, top: 30, bottom: 208, width: 648, height: 178 }
  const values = filtered.map((term) => term[key])
  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const padding = 0.3
  let domainMin = Math.max(0, rawMin - padding)
  let domainMax = Math.min(4, rawMax + padding)
  if (domainMax - domainMin < 0.6) {
    const center = (rawMin + rawMax) / 2 || rawMin || 2
    domainMin = Math.max(0, center - 0.35)
    domainMax = Math.min(4, center + 0.35)
  }
  if (domainMax - domainMin < 0.35) {
    domainMin = Math.max(0, domainMin - 0.2)
    domainMax = Math.min(4, domainMax + 0.2)
  }

  const yFor = (value) => {
    const ratio = (value - domainMin) / Math.max(domainMax - domainMin, 0.001)
    return chart.bottom - ratio * chart.height
  }

  const spreadRatio = filtered.length <= 2 ? 0.42 : filtered.length === 3 ? 0.58 : filtered.length === 4 ? 0.72 : 1
  const activeWidth = chart.width * spreadRatio
  const offsetX = chart.left + (chart.width - activeWidth) / 2

  const points = filtered.map((term, index) => {
    const x = filtered.length === 1 ? chart.left + chart.width / 2 : offsetX + (index * activeWidth) / (filtered.length - 1)
    const y = yFor(term[key])
    return {
      label: term.term || `Term ${index + 1}`,
      value: term[key],
      x,
      y,
    }
  })

  const ticks = Array.from({ length: 5 }, (_, index) => {
    const value = domainMin + ((domainMax - domainMin) * (4 - index)) / 4
    return {
      value,
      y: yFor(value),
    }
  })

  const linePath = buildLinePath(points)
  const areaPath = buildAreaPath(points, chart.bottom)

  return {
    points,
    ticks,
    areaPath,
    linePath,
    domain: { min: domainMin, max: domainMax },
    chart,
  }
}

function buildLinePath(points) {
  if (!points.length) return ''
  return points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')
}

function buildAreaPath(points, baselineY) {
  if (!points.length) return ''
  const linePath = buildLinePath(points)
  const last = points[points.length - 1]
  const first = points[0]
  return `${linePath} L ${last.x} ${baselineY} L ${first.x} ${baselineY} Z`
}

function renderCredits(courses) {
  return (courses ?? []).reduce((total, course) => {
    const credits = Number.parseFloat(course?.credits)
    const grade = String(course?.grade || '').toUpperCase()
    if (!Number.isFinite(credits) || UNEARNED_GRADES.has(grade)) return total
    return total + credits
  }, 0)
}

const ACORN_COLUMNS = [
  { key: 'courseCode', label: 'Course', type: 'text' },
  { key: 'title', label: 'Title', type: 'text' },
  { key: 'term', label: 'Term', type: 'term' },
  { key: 'credits', label: 'Credits', type: 'number' },
  { key: 'mark', label: 'Mark', type: 'number' },
  { key: 'grade', label: 'Grade', type: 'text' },
  { key: 'courseAverage', label: 'Course Avg', type: 'text' },
]

function compareAcornRows(left, right, sortKey, type, direction) {
  const leftValue = left?.[sortKey]
  const rightValue = right?.[sortKey]
  const isDescending = direction === 'desc'

  if (type === 'number') {
    const leftNumber = Number.parseFloat(leftValue)
    const rightNumber = Number.parseFloat(rightValue)
    const leftMissing = !Number.isFinite(leftNumber)
    const rightMissing = !Number.isFinite(rightNumber)
    if (leftMissing && rightMissing) return 0
    if (leftMissing) return 1
    if (rightMissing) return -1
    return isDescending ? rightNumber - leftNumber : leftNumber - rightNumber
  }

  if (type === 'term') {
    const leftMissing = !String(leftValue || '').trim()
    const rightMissing = !String(rightValue || '').trim()
    if (leftMissing && rightMissing) return 0
    if (leftMissing) return 1
    if (rightMissing) return -1
    const termCmp = sortTerms({ term: leftValue }, { term: rightValue })
    if (termCmp !== 0) return isDescending ? -termCmp : termCmp
    const fallback = String(left?.courseCode || '').localeCompare(String(right?.courseCode || ''))
    return isDescending ? -fallback : fallback
  }

  const leftMissing = !String(leftValue || '').trim()
  const rightMissing = !String(rightValue || '').trim()
  if (leftMissing && rightMissing) return 0
  if (leftMissing) return 1
  if (rightMissing) return -1

  const result = String(leftValue || '').localeCompare(String(rightValue || ''), undefined, {
    numeric: true,
    sensitivity: 'base',
  })
  return isDescending ? -result : result
}

function SummaryCard({ label, value, hint }) {
  return (
    <div className="acorn-summary-card">
      <div className="acorn-summary-label">{label}</div>
      <div className="acorn-summary-value">{value}</div>
      {hint ? <div className="acorn-summary-hint">{hint}</div> : null}
    </div>
  )
}

function AcornOnboarding({ importCode, status, claimError, claimPending, onClaim, onRefreshCode }) {
  const detected = Boolean(status?.exists)

  return (
    <div className="page dashboard-page acorn-page">
      <div className="acorn-hero rise">
        <div>
          <div className="section-label">ACORN Import</div>
          <h1 className="acorn-page-title">Bring in your academic history</h1>
          <p className="acorn-page-copy">
            Import your ACORN history once through the Chrome extension and keep it linked to your account for future
            visits.
          </p>
        </div>
        <div className={`acorn-status-card ${detected ? 'detected' : ''}`}>
          <div className="acorn-status-label">Import status</div>
          <div className="acorn-status-value">{detected ? 'Import detected' : 'Waiting for import'}</div>
          <div className="acorn-status-meta">
            {detected
              ? `${status.courseCount ?? 0} courses found · ${formatTimestamp(status.importedAt)}`
              : 'Paste the code below into the extension, then import from ACORN.'}
          </div>
        </div>
      </div>

      <div className="acorn-onboarding-grid">
        <section className="acorn-onboarding-card rise">
          <div className="acorn-panel-title">How it works</div>
          <ol className="acorn-steps">
            <li>Install the UofT Agent Chrome extension.</li>
            <li>Open your ACORN Academic History page in another tab.</li>
            <li>Paste this import code into the extension popup.</li>
            <li>Click import, then return here and confirm.</li>
          </ol>
          <div className="acorn-actions">
            <a className="acorn-primary-btn" href={ACORN_EXTENSION_URL} target="_blank" rel="noreferrer">
              Install extension
            </a>
            <button className="acorn-secondary-btn" type="button" onClick={onRefreshCode}>
              Generate new code
            </button>
          </div>
        </section>

        <section className="acorn-code-card rise">
          <div className="acorn-panel-title">Your import code</div>
          <div className="acorn-code">{importCode}</div>
          <div className="acorn-code-help">Paste this exact code into the extension before importing from ACORN.</div>
          <div className="acorn-code-actions">
            <button
              className="acorn-secondary-btn"
              type="button"
              onClick={() => navigator.clipboard?.writeText(importCode)}
            >
              Copy code
            </button>
            <button className="acorn-primary-btn" type="button" onClick={onClaim} disabled={claimPending}>
              {claimPending ? 'Checking import…' : "I've completed the import"}
            </button>
          </div>
          {claimError ? <div className="acorn-inline-error">{claimError}</div> : null}
          {!claimError && !detected ? (
            <div className="acorn-inline-note">
              No import has been found for this code yet. Complete the extension import, then try again.
            </div>
          ) : null}
          {detected ? (
            <div className="acorn-inline-success">
              Import detected. You can confirm now to link it to your account.
            </div>
          ) : null}
        </section>
      </div>
    </div>
  )
}

function AcornLanding({ data, onReimport }) {
  const courses = data?.courses ?? []
  const terms = useMemo(() => [...(data?.terms ?? [])].sort(sortTerms), [data?.terms])
  const [gpaView, setGpaView] = useState('sessionalGpa')
  const [hoveredIndex, setHoveredIndex] = useState(null)
  const [sortConfig, setSortConfig] = useState({ key: 'mark', direction: 'desc' })

  const totalCredits = useMemo(() => renderCredits(courses), [courses])
  const latestCumulative = useMemo(() => {
    const candidates = terms.filter((term) => typeof term?.cumulativeGpa === 'number')
    return candidates.length ? candidates[candidates.length - 1].cumulativeGpa : null
  }, [terms])
  const chartData = useMemo(() => buildTrendChart(terms, gpaView), [gpaView, terms])
  const hoveredPoint = hoveredIndex === null ? null : chartData.points[hoveredIndex] ?? null
  const rows = useMemo(() => {
    const next = [...courses]
    const column = ACORN_COLUMNS.find((entry) => entry.key === sortConfig.key) ?? ACORN_COLUMNS[2]
    next.sort((a, b) => {
      return compareAcornRows(a, b, column.key, column.type, sortConfig.direction)
    })
    return next
  }, [courses, sortConfig])

  function handleSort(columnKey) {
    setSortConfig((current) =>
      current.key === columnKey
        ? { key: columnKey, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key: columnKey, direction: 'asc' },
    )
  }

  return (
    <div className="page dashboard-page acorn-page">
      <div className="acorn-header rise">
        <div>
          <div className="section-label">ACORN</div>
          <h1 className="acorn-page-title">Academic history</h1>
          <p className="acorn-page-copy">Imported from ACORN and linked to your account for planning and record review.</p>
        </div>
        <div className="acorn-header-actions">
          <div className="acorn-last-import">Last imported {formatTimestamp(data?.importedAt)}</div>
          <button className="acorn-secondary-btn" type="button" onClick={onReimport}>
            Re-import data
          </button>
        </div>
      </div>

      <section className="acorn-summary-grid rise">
        <SummaryCard label="Courses Imported" value={String(courses.length)} />
        <SummaryCard label="Credits Earned" value={totalCredits.toFixed(1)} />
        {latestCumulative !== null ? (
          <SummaryCard label="Cumulative GPA" value={latestCumulative.toFixed(2)} />
        ) : (
          <SummaryCard label="Cumulative GPA" value="—" hint="No numeric GPA parsed yet" />
        )}
      </section>

      {terms.length ? (
        <section className="acorn-chart-card rise">
          <div className="acorn-panel-head">
            <div>
              <div className="acorn-panel-title">GPA trend</div>
              <div className="acorn-panel-sub">Sessional and cumulative GPA history from your imported ACORN terms.</div>
            </div>
            <div className="acorn-toggle">
              <button
                className={`acorn-toggle-btn ${gpaView === 'sessionalGpa' ? 'active' : ''}`}
                type="button"
                onClick={() => setGpaView('sessionalGpa')}
              >
                Sessional
              </button>
              <button
                className={`acorn-toggle-btn ${gpaView === 'cumulativeGpa' ? 'active' : ''}`}
                type="button"
                onClick={() => setGpaView('cumulativeGpa')}
              >
                Cumulative
              </button>
            </div>
          </div>

          {chartData.points.length ? (
            <div className="acorn-chart-wrap">
              <svg className="acorn-chart" viewBox="0 0 760 252" preserveAspectRatio="xMidYMid meet">
                <defs>
                  <linearGradient id="acornAreaGradient" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="oklch(68% 0.16 240 / 0.32)" />
                    <stop offset="100%" stopColor="oklch(68% 0.16 240 / 0.02)" />
                  </linearGradient>
                </defs>
                <line className="acorn-axis-line" x1={chartData.chart.left} y1={chartData.chart.top} x2={chartData.chart.left} y2={chartData.chart.bottom} />
                <line className="acorn-axis-line" x1={chartData.chart.left} y1={chartData.chart.bottom} x2={chartData.chart.right} y2={chartData.chart.bottom} />
                {chartData.ticks.map((tick) => {
                  return (
                    <g key={tick.value.toFixed(2)}>
                      <line className="acorn-grid-line" x1={chartData.chart.left} y1={tick.y} x2={chartData.chart.right} y2={tick.y} />
                      <text className="acorn-axis-label" x="24" y={tick.y + 4}>
                        {tick.value.toFixed(2)}
                      </text>
                    </g>
                  )
                })}
                <path className="acorn-area" d={chartData.areaPath} />
                <path className="acorn-line" d={chartData.linePath} />
                {hoveredPoint ? (
                  <g className="acorn-hover-state">
                    <line
                      className="acorn-hover-line"
                      x1={hoveredPoint.x}
                      y1={chartData.chart.top}
                      x2={hoveredPoint.x}
                      y2={chartData.chart.bottom}
                    />
                    <rect
                      className="acorn-tooltip-card"
                      x={Math.min(Math.max(hoveredPoint.x - 58, chartData.chart.left + 8), chartData.chart.right - 126)}
                      y={Math.max(hoveredPoint.y - 52, chartData.chart.top + 8)}
                      width="126"
                      height="40"
                      rx="10"
                    />
                    <text
                      className="acorn-tooltip-title"
                      x={Math.min(Math.max(hoveredPoint.x - 46, chartData.chart.left + 18), chartData.chart.right - 114)}
                      y={Math.max(hoveredPoint.y - 34, chartData.chart.top + 24)}
                    >
                      {hoveredPoint.label}
                    </text>
                    <text
                      className="acorn-tooltip-value"
                      x={Math.min(Math.max(hoveredPoint.x - 46, chartData.chart.left + 18), chartData.chart.right - 114)}
                      y={Math.max(hoveredPoint.y - 16, chartData.chart.top + 42)}
                    >
                      GPA {hoveredPoint.value.toFixed(2)}
                    </text>
                  </g>
                ) : null}
                {chartData.points.map((point, index) => (
                  <g key={point.label}>
                    <circle
                      className={`acorn-point ${index === chartData.points.length - 1 ? 'latest' : ''} ${hoveredIndex === index ? 'hovered' : ''}`}
                      cx={point.x}
                      cy={point.y}
                      r={hoveredIndex === index ? '7' : index === chartData.points.length - 1 ? '6' : '5'}
                    />
                    <text className="acorn-point-value" x={point.x} y={point.y - 12}>
                      {point.value.toFixed(2)}
                    </text>
                    <text className="acorn-axis-label" x={point.x} y="234" textAnchor="middle">
                      {point.label}
                    </text>
                    <circle
                      className="acorn-hit-area"
                      cx={point.x}
                      cy={point.y}
                      r="18"
                      onMouseEnter={() => setHoveredIndex(index)}
                      onMouseLeave={() => setHoveredIndex((current) => (current === index ? null : current))}
                    />
                  </g>
                ))}
              </svg>
            </div>
          ) : (
            <div className="empty-card">No numeric GPA values were found in the imported terms yet.</div>
          )}
        </section>
      ) : null}

      <section className="acorn-table-card rise">
        <div className="acorn-panel-head">
          <div>
            <div className="acorn-panel-title">Imported courses</div>
            <div className="acorn-panel-sub">Your saved ACORN history, grouped as a clean read-only reference.</div>
          </div>
        </div>

        {rows.length ? (
          <div className="acorn-table-scroll">
            <table className="acorn-table">
              <thead>
                <tr>
                  {ACORN_COLUMNS.map((column) => {
                    const isActive = sortConfig.key === column.key
                    const direction = isActive ? sortConfig.direction : null
                    return (
                      <th key={column.key} scope="col">
                        <button
                          className={`acorn-sort-btn ${isActive ? 'active' : ''}`}
                          type="button"
                          onClick={() => handleSort(column.key)}
                        >
                          <span>{column.label}</span>
                          <span className="acorn-sort-icon" aria-hidden="true">
                            {direction === 'asc' ? '↑' : direction === 'desc' ? '↓' : '↕'}
                          </span>
                        </button>
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {rows.map((course, index) => (
                  <tr key={`${course.courseCode}-${course.term ?? 'none'}-${index}`}>
                    <td className="acorn-course-code">{course.courseCode || '—'}</td>
                    <td>{course.title || 'Untitled course'}</td>
                    <td>{course.term || 'Transfer / Unassigned'}</td>
                    <td>{course.credits || '—'}</td>
                    <td>{course.mark || '—'}</td>
                    <td>{course.grade || '—'}</td>
                    <td>{course.courseAverage || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-card">ACORN data exists, but no parsed courses were stored.</div>
        )}
      </section>
    </div>
  )
}

export default function Acorn() {
  const queryClient = useQueryClient()
  const [importCode, setImportCode] = useState(() => ensureImportCode())
  const [reimportMode, setReimportMode] = useState(false)
  const [claimError, setClaimError] = useState('')

  useEffect(() => {
    window.localStorage.setItem(IMPORT_CODE_KEY, importCode)
  }, [importCode])

  const acornQuery = useQuery({
    queryKey: ['acorn'],
    queryFn: async () => {
      const response = await client.get('/api/acorn/me')
      return response.data.data
    },
  })

  const statusQuery = useQuery({
    queryKey: ['acorn-status', importCode],
    queryFn: async () => {
      const response = await client.get('/api/acorn/status', {
        params: { import_code: importCode },
      })
      return response.data
    },
    enabled: !acornQuery.data || reimportMode,
    refetchInterval: 10000,
  })

  const claimMutation = useMutation({
    mutationFn: async () => {
      const response = await client.post('/api/acorn/claim', { import_code: importCode })
      return response.data.data
    },
    onSuccess: async (next) => {
      if (!next) {
        setClaimError('No ACORN import was found for this code yet. Complete the extension import first.')
        return
      }
      setClaimError('')
      setReimportMode(false)
      const nextCode = resetImportCode()
      setImportCode(nextCode)
      await queryClient.invalidateQueries({ queryKey: ['acorn'] })
      await queryClient.invalidateQueries({ queryKey: ['acorn-status'] })
    },
    onError: (error) => {
      setClaimError(error?.response?.data?.error || 'Could not link the imported ACORN data to your account.')
    },
  })

  function handleReimport() {
    setClaimError('')
    setReimportMode(true)
    setImportCode(resetImportCode())
  }

  if (acornQuery.isLoading) {
    return (
      <div className="page dashboard-page acorn-page">
        <div className="dashboard-loading-card" aria-live="polite">
          <div className="loading-spinner" aria-hidden="true" />
          <div className="dashboard-loading-copy">Loading ACORN data…</div>
        </div>
      </div>
    )
  }

  if (acornQuery.error) {
    return (
      <div className="page dashboard-page acorn-page">
        <div className="empty-card">Failed to load your ACORN data.</div>
      </div>
    )
  }

  if (acornQuery.data && !reimportMode) {
    return <AcornLanding data={acornQuery.data} onReimport={handleReimport} />
  }

  return (
    <AcornOnboarding
      importCode={importCode}
      status={statusQuery.data}
      claimError={claimError}
      claimPending={claimMutation.isPending}
      onClaim={() => claimMutation.mutate()}
      onRefreshCode={() => {
        setClaimError('')
        setImportCode(resetImportCode())
      }}
    />
  )
}
