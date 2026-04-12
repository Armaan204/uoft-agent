// This extension does not collect credentials and does not perform login.
// It only handles extracted academic history after the user is already
// authenticated inside ACORN in their own browser session.
const LOG_PREFIX = "[ACORN-EXT]";
const BACKEND_URL = "https://uoft-agent-production.up.railway.app/api/acorn/import";
const DEBUG = false;

function log(...args) {
  if (DEBUG) {
    console.log(LOG_PREFIX, ...args);
  }
}

function getActiveAcornTab() {
  return chrome.tabs.query({
    active: true,
    currentWindow: true,
    url: ["https://acorn.utoronto.ca/*"]
  });
}

function sendMessageToTab(tabId, message) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(response);
    });
  });
}

function storeExtraction(payload) {
  return new Promise((resolve, reject) => {
    chrome.storage.local.set({ lastAcademicHistoryImport: payload }, () => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve();
    });
  });
}

async function sendToBackend(data) {
  log("Sending extracted ACORN data to backend:", BACKEND_URL);

  const response = await fetch(BACKEND_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(data)
  });

  const responseText = await response.text();
  log("Backend response status:", response.status);
  log("Backend response body:", responseText);

  if (!response.ok) {
    throw new Error(`Backend request failed (${response.status}): ${responseText || response.statusText}`);
  }

  return {
    status: response.status,
    body: responseText
  };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.action !== "EXTRACT_ACORN_DATA") {
    return;
  }

  (async () => {
    try {
      const tabs = await getActiveAcornTab();
      const activeTab = tabs[0];
      if (!activeTab?.id) {
        sendResponse({ ok: false, error: "Open an ACORN tab first." });
        return;
      }

      log("Forwarding extraction request to tab:", activeTab.id);
      let extractionResult;
      try {
        extractionResult = await sendMessageToTab(activeTab.id, { action: "EXTRACT_ACORN_DATA" });
      } catch (msgError) {
        const msg = msgError instanceof Error ? msgError.message : String(msgError);
        const isStaleTab = msg.includes("Receiving end does not exist") ||
                           msg.includes("Could not establish connection");
        if (!isStaleTab) {
          sendResponse({ ok: false, error: msg });
          return;
        }
        // Content script invalidated after extension update — re-inject and retry once.
        log("Content script not found, re-injecting into tab:", activeTab.id);
        try {
          await chrome.scripting.executeScript({ target: { tabId: activeTab.id }, files: ["content.js"] });
          await new Promise((r) => setTimeout(r, 300));
          extractionResult = await sendMessageToTab(activeTab.id, { action: "EXTRACT_ACORN_DATA" });
        } catch (_retryError) {
          sendResponse({ ok: false, error: "Could not reach the ACORN tab. Please reload it and try again." });
          return;
        }
      }

      if (!extractionResult?.ok) {
        sendResponse({
          ok: false,
          error: extractionResult?.error || "Extraction failed."
        });
        return;
      }

      const payload = {
        terms: Array.isArray(extractionResult.terms) ? extractionResult.terms : undefined,
        courses: Array.isArray(extractionResult.courses) ? extractionResult.courses : [],
        importCode: String(message.importCode || "").trim(),
        source: "acorn",
        capturedAt: new Date().toISOString(),
        sourceUrl: activeTab.url || null
      };

      if (!payload.importCode) {
        sendResponse({ ok: false, error: "Missing import code." });
        return;
      }

      await storeExtraction(payload);
      log("Stored extracted ACORN data:", payload);

      let backendResult = null;
      try {
        backendResult = await sendToBackend(payload);
      } catch (error) {
        sendResponse({
          ok: false,
          error: error instanceof Error
            ? `Backend unavailable: ${error.message}`
            : String(error)
        });
        return;
      }

      sendResponse({
        ok: true,
        message: "Imported successfully",
        courseCount: payload.courses.length,
        backend: backendResult
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
