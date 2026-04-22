export default function Logo({ compact = false }) {
  return (
    <div className="brand">
      <div className="brand-icon">
        <svg viewBox="0 0 28 28" fill="none" aria-hidden="true">
          <path d="M14 6L3 11.5L14 17L25 11.5L14 6Z" fill="oklch(68% 0.16 240)" opacity="0.9" />
          <path
            d="M8 14.2V19.5C8 19.5 10.5 21.5 14 21.5C17.5 21.5 20 19.5 20 19.5V14.2L14 17L8 14.2Z"
            fill="oklch(68% 0.16 240)"
            opacity="0.55"
          />
          <circle cx="22.5" cy="8" r="1.1" fill="oklch(80% 0.12 200)" opacity="0.8" />
        </svg>
      </div>
      {!compact && <span className="brand-name">UofT Agent</span>}
    </div>
  )
}
