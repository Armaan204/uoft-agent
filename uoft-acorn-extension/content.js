(async () => {
  // This content script does not handle login or credentials.
  // It only reads the already-visible ACORN academic-history page after the
  // user has logged in normally and clicked the popup action.
  const parser = await import(chrome.runtime.getURL("utils/parser.js"));
  const LOG_PREFIX = "[ACORN-EXT]";
  const DEBUG = false;

  function log(...args) {
    if (DEBUG) {
      console.log(LOG_PREFIX, ...args);
    }
  }

  async function waitForCourses() {
    for (let i = 0; i < 10; i += 1) {
      const exists = document.querySelector("div.courses.blok");
      if (exists) {
        return;
      }
      await new Promise((r) => setTimeout(r, 500));
    }
  }

  function isAcademicHistoryPage() {
    const bodyText = document.body?.innerText?.toLowerCase() || "";
    const hasHistoryHeading =
      bodyText.includes("academic history") ||
      bodyText.includes("complete academic history") ||
      bodyText.includes("crs code title wgt mrk grd crsavg");

    return hasHistoryHeading;
  }

  /**
   * Parse sessional and cumulative GPA from a .gpa-listing div's text.
   * Returns { sessionalGpa, cumulativeGpa, status } — any field may be null.
   */
  function parseGpaListing(text) {
    const normalised = (text || "").replace(/\s+/g, " ").trim();
    const sessMatch = normalised.match(/Sessional\s+GPA\s+([\d.]+)/i);
    const cumMatch = normalised.match(/Cumulative\s+GPA\s+([\d.]+)/i);
    const statusMatch = normalised.match(/Status:\s*(.+)/i);
    return {
      sessionalGpa: sessMatch ? parseFloat(sessMatch[1]) : null,
      cumulativeGpa: cumMatch ? parseFloat(cumMatch[1]) : null,
      status: statusMatch ? statusMatch[1].trim() : null,
    };
  }

  // "2022 Fall - Honours Bachelor of Science (Statistics Co-op)"
  const TERM_HEADING_RE = /^\d{4}\s+(?:Fall|Winter|Summer)\s+-\s+\S/i;
  // "2022 Fall-2026 Winter: University of Toronto Scarborough"
  const ENROLLMENT_PERIOD_RE = /^(\d{4}\s+(?:Fall|Winter|Summer))\s*-\s*(\d{4}\s+(?:Fall|Winter|Summer))\s*:\s*(.+)$/i;
  // "In Progress - 2023 Summer - Specialist (Co-operative) Program in Statistics..."
  const STATUS_LINE_RE = /^(In\s+Progress|Graduated|Suspended|Withdrawn|Transferred|Inactive)\s*-\s*(.+)$/i;
  // "2023 Summer - Specialist (Co-operative) Program in Statistics..."
  const SESSION_PREFIX_RE = /^(\d{4}\s+(?:Fall|Winter|Summer))\s*-\s*(.+)$/i;

  function isTermHeading(text) {
    return TERM_HEADING_RE.test(text);
  }

  function parsePrograms(infoSections) {
    const programs = [];

    for (let i = 0; i < infoSections.length; i++) {
      const text = (infoSections[i].textContent || "").replace(/\s+/g, " ").trim();
      const periodMatch = text.match(ENROLLMENT_PERIOD_RE);
      if (!periodMatch) continue;

      const enrollmentPeriod = `${periodMatch[1].trim()}-${periodMatch[2].trim()}`;
      const institution = periodMatch[3].trim();

      for (let j = i + 1; j < infoSections.length; j++) {
        const rawText = (infoSections[j].innerText || infoSections[j].textContent || "");
        const lines = rawText.split("\n").map((l) => l.replace(/\s+/g, " ").trim()).filter(Boolean);

        let shouldBreak = false;
        for (const nextText of lines) {
          if (TERM_HEADING_RE.test(nextText) || ENROLLMENT_PERIOD_RE.test(nextText)) {
            shouldBreak = true;
            break;
          }
          const statusMatch = nextText.match(STATUS_LINE_RE);
          if (statusMatch) {
            const enrollmentStatus = statusMatch[1].replace(/\s+/g, " ").trim();
            const rest = statusMatch[2].trim();
            let startSession = null;
            let programName = null;
            const sessionMatch = rest.match(SESSION_PREFIX_RE);
            if (sessionMatch) {
              startSession = sessionMatch[1].trim();
              programName = sessionMatch[2].trim();
            } else {
              programName = rest;
            }
            programs.push({ enrollmentPeriod, institution, enrollmentStatus, startSession, programName });
          }
        }
        if (shouldBreak) break;
      }
    }

    return programs;
  }

  /**
   * Parse courses from a div.courses.blok element.
   * Each course is tagged with the given termName.
   */
  function parseCoursesBlock(blockEl, termName) {
    const blockText = (blockEl.innerText || "").replace(/\s+/g, " ").trim();
    const segments = blockText
      .split(/(?=(?:[A-Z]{4}\d{2}|[A-Z]{3}\d{3})[A-Z]\d|[A-Z]{4}\*{3})/)
      .map((s) => s.trim())
      .filter(Boolean);

    const courses = [];
    for (const segment of segments) {
      const course = parser.parseCourseSegment(segment);
      if (course) {
        courses.push({ ...course, term: termName });
      }
    }
    return courses;
  }

  async function extractAcademicHistory() {
    if (!isAcademicHistoryPage()) {
      return { error: "Not on supported ACORN page" };
    }

    if (document.querySelector('a[data-ng-click="$ctrl.getComplete()"]')) {
      return { error: "Click on Complete Academic History." };
    }

    await waitForCourses();

    const infoSections = Array.from(document.querySelectorAll("p.info-section"));
    log("Found info-section headings:", infoSections.length);

    const terms = [];
    const processedBlocks = new Set();

    const programs = parsePrograms(infoSections);
    log("Parsed programs:", programs.length);

    for (const infoSection of infoSections) {
      const termText = (infoSection.textContent || "").replace(/\s+/g, " ").trim();
      if (!isTermHeading(termText)) {
        continue;
      }
      // "2022 Fall - Honours Bachelor of Science (Statistics Co-op)" → "2022 Fall"
      const termName = termText.split(" - ")[0].trim();

      const termData = {
        term: termName,
        sessionalGpa: null,
        cumulativeGpa: null,
        status: null,
        courses: [],
      };

      // Walk siblings until the next info-section or end of parent.
      let sibling = infoSection.nextElementSibling;
      while (sibling && !sibling.matches("p.info-section")) {
        if (sibling.classList.contains("gpa-listing")) {
          const parsed = parseGpaListing(sibling.textContent);
          if (parsed.sessionalGpa !== null) termData.sessionalGpa = parsed.sessionalGpa;
          if (parsed.cumulativeGpa !== null) termData.cumulativeGpa = parsed.cumulativeGpa;
          if (parsed.status !== null) termData.status = parsed.status;
        }

        if (sibling.classList.contains("courses") && sibling.classList.contains("blok")) {
          processedBlocks.add(sibling);
          const courses = parseCoursesBlock(sibling, termName);
          termData.courses.push(...courses);
          log("Parsed courses for", termName, ":", courses.length);
        }

        sibling = sibling.nextElementSibling;
      }

      terms.push(termData);
    }

    // Capture any .courses.blok not under a term heading (e.g. transfer credits block).
    const transferCourses = [];
    const allBlocks = document.querySelectorAll("div.courses.blok");
    for (const block of allBlocks) {
      if (!processedBlocks.has(block)) {
        const courses = parseCoursesBlock(block, null);
        transferCourses.push(...courses);
        log("Parsed transfer/unterm'd courses:", courses.length);
      }
    }

    const allCourses = [...terms.flatMap((t) => t.courses), ...transferCourses];
    log("Total terms:", terms.length, "Total courses:", allCourses.length, "Transfer:", transferCourses.length);

    if (!allCourses.length) {
      return { error: "ACORN structure found, but no courses parsed" };
    }

    return {
      ok: true,
      terms,
      courses: allCourses,
      programs,
    };
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || message.action !== "EXTRACT_ACORN_DATA") {
      return;
    }

    // Extraction is user-triggered from the popup. It does not run automatically.
    (async () => {
      try {
        const result = await extractAcademicHistory();
        if (!result.ok) {
          sendResponse(result);
          return;
        }

        sendResponse({
          ok: true,
          terms: result.terms,
          courses: result.courses,
          programs: result.programs,
        });
      } catch (error) {
        sendResponse({
          ok: false,
          error: error instanceof Error ? error.message : String(error)
        });
      }
    })();

    return true;
  });
})();
