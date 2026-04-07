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
      const exists = document.querySelector("div.courses");
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

  async function extractAcademicHistory() {
    if (!isAcademicHistoryPage()) {
      return { error: "Not on supported ACORN page" };
    }

    await waitForCourses();

    const blocks = Array.from(document.querySelectorAll("div.courses"));
    log("Found course blocks:", blocks.length);

    const courses = [];
    for (const block of blocks) {
      const text = (block.innerText || "").replace(/\s+/g, " ").trim();
      const segments = text
        .split(/(?=[A-Z]{4}\d{2}[A-Z]\d)/)
        .map((segment) => segment.trim())
        .filter(Boolean);

      log("Matches found in block:", segments.length);

      for (const segment of segments) {
        const course = parser.parseCourseSegment(segment);
        if (!course) {
          continue;
        }

        log("Parsed course:", course.courseCode, course.grade);
        courses.push(course);
      }
    }

    log("Parsed courses:", courses.length);

    if (!courses.length) {
      return { error: "ACORN structure found, but no courses parsed" };
    }

    return {
      ok: true,
      courses
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
          courses: result.courses
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
