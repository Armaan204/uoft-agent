export function getInitials(nameOrEmail) {
  return (nameOrEmail || 'UA')
    .replace(/@.*$/, '')
    .split(/[.\s_-]+/)
    .map((part) => part[0]?.toUpperCase())
    .join('')
    .slice(0, 2)
}
