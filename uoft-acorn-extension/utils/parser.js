function normalizeText(value) {
  return (value || "").replace(/\s+/g, " ").trim();
}

function isGradeToken(token) {
  return /^(A|B|C|D|F)[+-]?$/i.test(token) || ["NCR", "CR", "NGA", "IPR", "LWD", "GWR", "SDF", "WD", "P", "FL%", "NC%", "F"].includes(token.toUpperCase());
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

// Matches all UofT campus course code formats plus transfer credit codes:
//   UTSC:       4 letters + 2 digits + letter + digit  (CSCA08H3)
//   St. George / UTM: 3 letters + 3 digits + letter + digit  (CSC490H1, ECO101H5)
//   Transfer:   4 letters + *** (CSCA***)
const COURSE_CODE_RE = /^(?:[A-Z]{4}\d{2}|[A-Z]{3}\d{3})[A-Z]\d$|^[A-Z]{4}\*{3}$/;
const COURSE_CODE_START_RE = /^(?:[A-Z]{4}\d{2}|[A-Z]{3}\d{3})[A-Z]\d|^[A-Z]{4}\*{3}/;

export function parseCourseSegment(segment) {
  const rawText = normalizeText(segment);
  if (!rawText || !COURSE_CODE_START_RE.test(rawText)) {
    return null;
  }

  const tokens = rawText.split(/\s+/).filter(Boolean);
  if (!tokens.length) {
    return null;
  }

  const courseCode = tokens[0];
  if (!COURSE_CODE_RE.test(courseCode)) {
    return null;
  }

  const creditIndex = tokens.findIndex((token) => isCreditToken(token));
  if (creditIndex <= 1) {
    return null;
  }

  let credits = tokens[creditIndex];
  const title = normalizeText(tokens.slice(1, creditIndex).join(" "));
  const trailingTokens = tokens.slice(creditIndex + 1);

  let mark = null;
  let grade = null;
  let courseAverage = null;

  for (const token of trailingTokens) {
    if (mark === null && isMarkToken(token)) {
      mark = token;
      continue;
    }

    if (grade === null && isGradeToken(token)) {
      grade = token.toUpperCase();
      continue;
    }

    // Second grade token is the course average.
    if (grade !== null && courseAverage === null && isGradeToken(token)) {
      courseAverage = token.toUpperCase();
      continue;
    }

    // Transfer-credit style codes like A08 / A30 / A36 should still be kept.
    if (grade === null && /^[A-Z]\d{2}$/.test(token)) {
      grade = token.toUpperCase();
    }
  }

  // Co-op milestone courses (COP prefix) carry no academic credit.
  if (courseCode.startsWith("COP")) {
    credits = "0.00";
  } else {
    // CR/NCR courses are worth 0.5 credits even when ACORN shows 0.00.
    const gradeUpper = grade ? grade.toUpperCase() : null;
    if ((gradeUpper === "CR") && credits === "0.00") {
      credits = "0.50";
    }
  }

  return {
    courseCode,
    title,
    credits,
    mark,
    grade,
    courseAverage,
    rawText
  };
}
