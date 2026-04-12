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

    await waitForCourses();

    const infoSections = Array.from(document.querySelectorAll("p.info-section"));
    log("Found info-section headings:", infoSections.length);

    const terms = [];
    const processedBlocks = new Set();

    for (const infoSection of infoSections) {
      // "2022 Fall - Honours Bachelor of Science (Statistics Co-op)" → "2022 Fall"
      const termText = (infoSection.textContent || "").trim();
      const termName = termText.split(" - ")[0].trim();
      if (!termName) {
        continue;
      }

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
