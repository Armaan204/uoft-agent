export default function AddCourseCard({ onClick }) {
  return (
    <button type="button" className="course-card add-course-card rise" onClick={onClick}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="28" height="28" aria-hidden="true">
        <path d="M12 5v14M5 12h14" strokeLinecap="round" />
      </svg>
      <span className="add-course-label">Add course</span>
    </button>
  )
}
