export function queryAllSafe(root, selector) {
  try {
    return Array.from((root || document).querySelectorAll(selector));
  } catch (_error) {
    return [];
  }
}

export function queryOneSafe(root, selector) {
  return queryAllSafe(root, selector)[0] || null;
}

export function getText(node) {
  return (node?.innerText || node?.textContent || "").replace(/\s+/g, " ").trim();
}

export function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
