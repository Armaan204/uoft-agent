import { useCallback, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import client from '../api/client'

const UNEARNED_GRADES = new Set(["NCR", "NGA", "IPR", "LWD", "GWR", "SDF", "WD", "FL%", "NC%", "F"])
const TERM_ORDER = {
  winter: 0,
  spring: 1,
  summer: 2,
  fall: 3,
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

function isEarnedCourse(course) {
  const grade = String(course?.grade || '').trim().toUpperCase()
  if (UNEARNED_GRADES.has(grade) || grade === 'F') return false

  const mark = Number.parseFloat(course?.mark)
  if (Number.isFinite(mark) && mark < 50) return false

  const credits = Number.parseFloat(course?.credits)
  if (!Number.isFinite(credits) || credits <= 0) return false

  return true
}

function shouldDeduplicateCourseCode(courseCode) {
  return Boolean(courseCode) && !courseCode.includes('***')
}

function renderCredits(courses) {
  const creditsByCourseCode = new Map()
  let totalCredits = 0

  for (const course of courses ?? []) {
    const courseCode = String(course?.courseCode || '').trim().toUpperCase()
    if (!courseCode || !isEarnedCourse(course)) continue

    const credits = Number.parseFloat(course?.credits)
    if (!shouldDeduplicateCourseCode(courseCode)) {
      totalCredits += credits
      continue
    }

    const current = creditsByCourseCode.get(courseCode) ?? 0
    if (credits > current) {
      creditsByCourseCode.set(courseCode, credits)
    }
  }

  return totalCredits + Array.from(creditsByCourseCode.values()).reduce((total, credits) => total + credits, 0)
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

function escapeCsvValue(value) {
  const normalized = String(value ?? '')
  if (/[",\n]/.test(normalized)) {
    return `"${normalized.replace(/"/g, '""')}"`
  }
  return normalized
}

function downloadCoursesCsv(rows) {
  const header = ACORN_COLUMNS.map((column) => escapeCsvValue(column.label)).join(',')
  const body = rows.map((course) =>
    ACORN_COLUMNS.map((column) => escapeCsvValue(course?.[column.key] ?? '—')).join(','),
  )
  const csv = [header, ...body].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  const stamp = new Date().toISOString().slice(0, 10)

  link.href = url
  link.download = `acorn-courses-${stamp}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
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

function AcornUpload({ onSuccess }) {
  const queryClient = useQueryClient()
  const fileInputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [dragActive, setDragActive] = useState(false)
  const [uploadError, setUploadError] = useState('')

  const uploadMutation = useMutation({
    mutationFn: async (pdfFile) => {
      const formData = new FormData()
      formData.append('file', pdfFile)
      const response = await client.post('/api/acorn/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return response.data.data
    },
    onSuccess: async () => {
      setUploadError('')
      setFile(null)
      await queryClient.invalidateQueries({ queryKey: ['acorn'] })
      onSuccess?.()
    },
    onError: (error) => {
      setUploadError(error?.response?.data?.error || 'Failed to parse the uploaded PDF. Please make sure it is a Complete Academic History PDF from ACORN.')
    },
  })

  function handleFile(selected) {
    setUploadError('')
    if (!selected) return
    if (!selected.name.toLowerCase().endsWith('.pdf')) {
      setUploadError('Please select a PDF file.')
      return
    }
    if (selected.size > 10 * 1024 * 1024) {
      setUploadError('File exceeds the 10 MB limit.')
      return
    }
    setFile(selected)
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragActive(false)
    const dropped = e.dataTransfer?.files?.[0]
    if (dropped) handleFile(dropped)
  }

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    setDragActive(true)
  }, [])

  const handleDragLeave = useCallback((e) => {
    e.preventDefault()
    setDragActive(false)
  }, [])

  return (
    <div className="page dashboard-page acorn-page">
      <div className="acorn-hero rise">
        <div>
          <div className="section-label">ACORN Import</div>
          <h1 className="acorn-page-title">Bring in your academic history</h1>
          <p className="acorn-page-copy">
            Upload your Complete Academic History PDF from ACORN to import your courses, grades, and GPA.
          </p>
        </div>
        <div className={`acorn-status-card ${file ? 'detected' : ''}`}>
          <div className="acorn-status-label">Upload status</div>
          <div className="acorn-status-value">{file ? 'Ready to upload' : 'No file selected'}</div>
          <div className="acorn-status-meta">
            {file
              ? `${file.name} · ${formatFileSize(file.size)}`
              : 'Select or drop your ACORN PDF below.'}
          </div>
        </div>
      </div>

      <div className="acorn-onboarding-grid">
        <section className="acorn-onboarding-card rise">
          <div className="acorn-panel-title">How it works</div>
          <ol className="acorn-steps">
            <li>
              Log into{' '}
              <a href="https://acorn.utoronto.ca" target="_blank" rel="noreferrer">
                ACORN
                <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" width="1em" height="1em" aria-hidden="true" style={{ marginLeft: 3, verticalAlign: '-0.15em' }}>
                  <path d="M11 8.5v3a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1h3M8.5 2H12v3.5M12 2 6.5 7.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </a>
              {' '}and navigate to <strong>Academic History</strong>, then <strong>Complete Academic History</strong>.
            </li>
            <li>Click on <strong> Print Academic History</strong> and save the PDF.</li>
            <li>Upload the PDF here using the drop zone.</li>
          </ol>
        </section>

        <section className="acorn-code-card rise">
          <div className="acorn-panel-title">Upload your PDF</div>
          <div
            className={`acorn-drop-zone ${dragActive ? 'drag-active' : ''} ${file ? 'has-file' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click() }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              className="acorn-file-input"
              onChange={(e) => handleFile(e.target.files?.[0])}
            />
            {file ? (
              <div className="acorn-drop-zone-content">
                <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <polyline points="9 15 12 12 15 15" className="acorn-upload-arrow" />
                </svg>
                <div className="acorn-drop-zone-name">{file.name}</div>
                <div className="acorn-drop-zone-size">{formatFileSize(file.size)}</div>
              </div>
            ) : (
              <div className="acorn-drop-zone-content">
                <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                <div className="acorn-drop-zone-label">Drop your PDF here or click to browse</div>
                <div className="acorn-drop-zone-hint">PDF up to 10 MB</div>
              </div>
            )}
          </div>
          <div className="acorn-code-actions">
            {file ? (
              <button
                className="acorn-secondary-btn"
                type="button"
                onClick={(e) => { e.stopPropagation(); setFile(null); setUploadError('') }}
              >
                Remove file
              </button>
            ) : null}
            <button
              className="acorn-primary-btn"
              type="button"
              disabled={!file || uploadMutation.isPending}
              onClick={() => { if (file) uploadMutation.mutate(file) }}
            >
              {uploadMutation.isPending ? 'Uploading…' : 'Upload and import'}
            </button>
          </div>
          {uploadError ? <div className="acorn-inline-error">{uploadError}</div> : null}
        </section>
      </div>
    </div>
  )
}

function ProgramsSection({ programs }) {
  if (!programs?.length) return null
  return (
    <section className="acorn-table-card rise">
      <div className="acorn-panel-title">Enrolled programs</div>
      <div className="acorn-program-list">
        {programs.map((program, index) => (
          <div key={index} className="acorn-program-item">
            <div className="acorn-program-name">{program.programName ?? '—'}</div>
            <div className="acorn-program-meta">
              {program.enrollmentStatus ? (
                <div className="acorn-program-field">
                  <div className="acorn-program-label">Status</div>
                  <div className={`acorn-program-status ${(program.enrollmentStatus || '').toLowerCase().replace(/\s+/g, '-')}`}>
                    {program.enrollmentStatus}
                  </div>
                </div>
              ) : null}
              {program.institution ? (
                <div className="acorn-program-field">
                  <div className="acorn-program-label">Institution</div>
                  <div className="acorn-program-value">{program.institution}</div>
                </div>
              ) : null}
              {program.enrollmentPeriod ? (
                <div className="acorn-program-field">
                  <div className="acorn-program-label">Enrollment period</div>
                  <div className="acorn-program-value">{program.enrollmentPeriod}</div>
                </div>
              ) : null}
              {program.startSession ? (
                <div className="acorn-program-field">
                  <div className="acorn-program-label">Start session</div>
                  <div className="acorn-program-value">{program.startSession}</div>
                </div>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function AcornLanding({ data, onReimport }) {
  const courses = data?.courses ?? []
  const programs = data?.programs ?? []
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

      <ProgramsSection programs={programs} />

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
                {chartData.points.map((point, index) => (
                  <g key={point.label}>
                    <circle
                      className={`acorn-point ${index === chartData.points.length - 1 ? 'latest' : ''} ${hoveredIndex === index ? 'hovered' : ''}`}
                      cx={point.x}
                      cy={point.y}
                      r={hoveredIndex === index ? '7' : index === chartData.points.length - 1 ? '6' : '5'}
                    />
                    <text
                      className="acorn-point-value"
                      x={point.x}
                      y={point.y - 12}
                      opacity={hoveredIndex === index ? 0 : 1}
                    >
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
                {hoveredPoint ? (
                  <g className="acorn-hover-state" pointerEvents="none">
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
          {rows.length ? (
            <button className="acorn-secondary-btn" type="button" onClick={() => downloadCoursesCsv(rows)}>
              Download CSV
            </button>
          ) : null}
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
                    <td>{isEarnedCourse(course) ? (course.credits || '—') : '0.00'}</td>
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
  const [showUpload, setShowUpload] = useState(false)

  const acornQuery = useQuery({
    queryKey: ['acorn'],
    queryFn: async () => {
      const response = await client.get('/api/acorn/me')
      return response.data.data
    },
  })

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

  if (acornQuery.data && !showUpload) {
    return <AcornLanding data={acornQuery.data} onReimport={() => setShowUpload(true)} />
  }

  return <AcornUpload onSuccess={() => setShowUpload(false)} />
}
