import { useMemo, useState } from 'react'

import { useDemoData } from '../../context/DemoDataContext'

const TERM_ORDER = { winter: 0, spring: 1, summer: 2, fall: 3 }

function termSortKey(term) {
  const normalized = String(term || '').trim()
  const match = normalized.match(/(20\d{2}).*?(winter|spring|summer|fall)/i)
  if (match) return [Number(match[1]), TERM_ORDER[match[2].toLowerCase()] ?? 9]
  return [0, 9]
}

function sortTerms(a, b) {
  const [yearA, seasonA] = termSortKey(a?.term)
  const [yearB, seasonB] = termSortKey(b?.term)
  if (yearA !== yearB) return yearA - yearB
  return seasonA - seasonB
}

function buildTrendChart(terms, key) {
  const filtered = (terms ?? []).filter((t) => typeof t?.[key] === 'number').sort(sortTerms)
  if (!filtered.length) return { points: [], ticks: [], areaPath: '', linePath: '', chart: { left: 56, right: 704, top: 30, bottom: 208, width: 648, height: 178 } }

  const chart = { left: 56, right: 704, top: 30, bottom: 208, width: 648, height: 178 }
  const values = filtered.map((t) => t[key])
  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const padding = 0.3
  let domainMin = Math.max(0, rawMin - padding)
  let domainMax = Math.min(4, rawMax + padding)
  if (domainMax - domainMin < 0.6) {
    const center = (rawMin + rawMax) / 2
    domainMin = Math.max(0, center - 0.35)
    domainMax = Math.min(4, center + 0.35)
  }

  const yFor = (v) => chart.bottom - ((v - domainMin) / Math.max(domainMax - domainMin, 0.001)) * chart.height
  const spreadRatio = filtered.length <= 2 ? 0.42 : filtered.length === 3 ? 0.58 : 0.72
  const activeWidth = chart.width * spreadRatio
  const offsetX = chart.left + (chart.width - activeWidth) / 2

  const points = filtered.map((t, i) => {
    const x = filtered.length === 1 ? chart.left + chart.width / 2 : offsetX + (i * activeWidth) / (filtered.length - 1)
    return { label: t.term, value: t[key], x, y: yFor(t[key]) }
  })

  const ticks = Array.from({ length: 5 }, (_, i) => {
    const value = domainMin + ((domainMax - domainMin) * (4 - i)) / 4
    return { value, y: yFor(value) }
  })

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${chart.bottom} L ${points[0].x} ${chart.bottom} Z`

  return { points, ticks, areaPath, linePath, chart }
}

function SummaryCard({ label, value }) {
  return (
    <div className="acorn-summary-card">
      <div className="acorn-summary-label">{label}</div>
      <div className="acorn-summary-value">{value}</div>
    </div>
  )
}

export default function DemoAcorn() {
  const { acorn } = useDemoData()
  const [gpaView, setGpaView] = useState('sessionalGpa')
  const [hoveredIndex, setHoveredIndex] = useState(null)

  const terms = useMemo(() => [...(acorn.terms ?? [])].sort(sortTerms), [acorn.terms])
  const chartData = useMemo(() => buildTrendChart(terms, gpaView), [terms, gpaView])
  const hoveredPoint = hoveredIndex === null ? null : chartData.points[hoveredIndex] ?? null
  const latestCumulative = terms.length ? terms[terms.length - 1].cumulativeGpa : null

  return (
    <div className="page dashboard-page acorn-page">
      <div className="acorn-header rise">
        <div>
          <div className="section-label">ACORN</div>
          <h1 className="acorn-page-title">Academic history</h1>
          <p className="acorn-page-copy">Sample ACORN data for demonstration purposes.</p>
        </div>
      </div>

      <section className="acorn-table-card rise">
        <div className="acorn-panel-title">Enrolled programs</div>
        <div className="acorn-program-list">
          {acorn.programs.map((p, i) => (
            <div key={i} className="acorn-program-item">
              <div className="acorn-program-name">{p.programName}</div>
              <div className="acorn-program-meta">
                <div className="acorn-program-field">
                  <div className="acorn-program-label">Status</div>
                  <div className="acorn-program-status invited">{p.enrollmentStatus}</div>
                </div>
                <div className="acorn-program-field">
                  <div className="acorn-program-label">Institution</div>
                  <div className="acorn-program-value">{p.institution}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="acorn-summary-grid rise">
        <SummaryCard label="Courses Imported" value={String(acorn.courses.length)} />
        <SummaryCard label="Credits Earned" value="4.0" />
        {latestCumulative !== null && <SummaryCard label="Cumulative GPA" value={latestCumulative.toFixed(2)} />}
      </section>

      {terms.length > 0 && (
        <section className="acorn-chart-card rise">
          <div className="acorn-panel-head">
            <div>
              <div className="acorn-panel-title">GPA trend</div>
              <div className="acorn-panel-sub">Sessional and cumulative GPA history from sample ACORN data.</div>
            </div>
            <div className="acorn-toggle">
              <button className={`acorn-toggle-btn ${gpaView === 'sessionalGpa' ? 'active' : ''}`} type="button" onClick={() => setGpaView('sessionalGpa')}>Sessional</button>
              <button className={`acorn-toggle-btn ${gpaView === 'cumulativeGpa' ? 'active' : ''}`} type="button" onClick={() => setGpaView('cumulativeGpa')}>Cumulative</button>
            </div>
          </div>

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
              {chartData.ticks.map((tick) => (
                <g key={tick.value.toFixed(2)}>
                  <line className="acorn-grid-line" x1={chartData.chart.left} y1={tick.y} x2={chartData.chart.right} y2={tick.y} />
                  <text className="acorn-axis-label" x="24" y={tick.y + 4}>{tick.value.toFixed(2)}</text>
                </g>
              ))}
              <path className="acorn-area" d={chartData.areaPath} />
              <path className="acorn-line" d={chartData.linePath} />
              {chartData.points.map((point, index) => (
                <g key={point.label}>
                  <circle
                    className={`acorn-point ${index === chartData.points.length - 1 ? 'latest' : ''} ${hoveredIndex === index ? 'hovered' : ''}`}
                    cx={point.x} cy={point.y}
                    r={hoveredIndex === index ? '7' : index === chartData.points.length - 1 ? '6' : '5'}
                  />
                  <text className="acorn-point-value" x={point.x} y={point.y - 12} opacity={hoveredIndex === index ? 0 : 1}>
                    {point.value.toFixed(2)}
                  </text>
                  <text className="acorn-axis-label" x={point.x} y="234" textAnchor="middle">{point.label}</text>
                  <circle className="acorn-hit-area" cx={point.x} cy={point.y} r="18"
                    onMouseEnter={() => setHoveredIndex(index)}
                    onMouseLeave={() => setHoveredIndex((c) => c === index ? null : c)}
                  />
                </g>
              ))}
              {hoveredPoint && (
                <g className="acorn-hover-state" pointerEvents="none">
                  <line className="acorn-hover-line" x1={hoveredPoint.x} y1={chartData.chart.top} x2={hoveredPoint.x} y2={chartData.chart.bottom} />
                  <rect className="acorn-tooltip-card" x={Math.min(Math.max(hoveredPoint.x - 58, chartData.chart.left + 8), chartData.chart.right - 126)} y={Math.max(hoveredPoint.y - 52, chartData.chart.top + 8)} width="126" height="40" rx="10" />
                  <text className="acorn-tooltip-title" x={Math.min(Math.max(hoveredPoint.x - 46, chartData.chart.left + 18), chartData.chart.right - 114)} y={Math.max(hoveredPoint.y - 34, chartData.chart.top + 24)}>{hoveredPoint.label}</text>
                  <text className="acorn-tooltip-value" x={Math.min(Math.max(hoveredPoint.x - 46, chartData.chart.left + 18), chartData.chart.right - 114)} y={Math.max(hoveredPoint.y - 16, chartData.chart.top + 42)}>GPA {hoveredPoint.value.toFixed(2)}</text>
                </g>
              )}
            </svg>
          </div>
        </section>
      )}

      <section className="acorn-table-card rise">
        <div className="acorn-panel-head">
          <div>
            <div className="acorn-panel-title">Imported courses</div>
            <div className="acorn-panel-sub">Sample course history for demonstration.</div>
          </div>
        </div>
        <div className="acorn-table-scroll">
          <table className="acorn-table">
            <thead>
              <tr>
                <th>Course</th>
                <th>Title</th>
                <th>Term</th>
                <th>Credits</th>
                <th>Mark</th>
                <th>Grade</th>
                <th>Course Avg</th>
              </tr>
            </thead>
            <tbody>
              {acorn.courses.map((c, i) => (
                <tr key={`${c.courseCode}-${i}`}>
                  <td className="acorn-course-code">{c.courseCode}</td>
                  <td>{c.title}</td>
                  <td>{c.term}</td>
                  <td>{c.credits}</td>
                  <td>{c.mark}</td>
                  <td>{c.grade}</td>
                  <td>{c.courseAverage}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
