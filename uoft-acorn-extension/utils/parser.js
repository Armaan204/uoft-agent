function normalizeText(value) {
  return (value || "").replace(/\s+/g, " ").trim();
}

function isGradeToken(token) {
  return /^(A|B|C|D|F)[+-]?$/i.test(token) || ["CR", "NGA", "IPR"].includes(token.toUpperCase());
}

function isCreditToken(token) {
  return /^\d+\.\d{2}$/.test(token);
}

function isMarkToken(token) {
  if (!/^\d{1,3}$/.test(token)) {
    return false;
  }
  const value = Number(token);
  return value >= 0 && value <= 100;
}

export function parseCourseSegment(segment) {
  const rawText = normalizeText(segment);
  if (!rawText || !/^[A-Z]{4}\d{2}[A-Z]\d/.test(rawText)) {
    return null;
  }

  const tokens = rawText.split(/\s+/).filter(Boolean);
  if (!tokens.length) {
    return null;
  }

  const courseCode = tokens[0];
  if (!/^[A-Z]{4}\d{2}[A-Z]\d$/.test(courseCode)) {
    return null;
  }

  const creditIndex = tokens.findIndex((token) => isCreditToken(token));
  if (creditIndex <= 1) {
    return null;
  }

  const credits = tokens[creditIndex];
  const title = normalizeText(tokens.slice(1, creditIndex).join(" "));
  const trailingTokens = tokens.slice(creditIndex + 1);

  let mark = null;
  let grade = null;

  for (const token of trailingTokens) {
    if (mark === null && isMarkToken(token)) {
      mark = token;
      continue;
    }

    if (grade === null && isGradeToken(token)) {
      grade = token.toUpperCase();
      continue;
    }

    // Transfer-credit style codes like A08 / A30 / A36 should still be kept.
    if (grade === null && /^[A-Z]\d{2}$/.test(token)) {
      grade = token.toUpperCase();
    }
  }

  return {
    courseCode,
    title,
    credits,
    mark,
    grade,
    rawText
  };
}
