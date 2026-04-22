export function displayCourseCode(courseCode) {
  const value = String(courseCode || '').trim()
  if (!value) return 'Course'
  return value.slice(0, 8)
}
