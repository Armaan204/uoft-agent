const importBtn = document.getElementById("importBtn");
const statusEl = document.getElementById("status");
const importCodeEl = document.getElementById("importCode");

// The popup only triggers extraction from an already logged-in ACORN tab.
// It does not ask for, store, or transmit credentials.
function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function sendRuntimeMessage(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(response);
    });
  });
}

function getStorageItem(key) {
  return new Promise((resolve, reject) => {
    chrome.storage.local.get([key], (result) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(result[key]);
    });
  });
}

function setStorageItem(key, value) {
  return new Promise((resolve, reject) => {
    chrome.storage.local.set({ [key]: value }, () => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve();
    });
  });
}

async function restoreImportCode() {
  try {
    const saved = await getStorageItem("importCode");
    if (saved && importCodeEl) {
      importCodeEl.value = saved;
    }
  } catch (_error) {
    // Keep the popup usable even if local storage is unavailable.
  }
}

restoreImportCode();

importBtn.addEventListener("click", async () => {
  try {
    const importCode = (importCodeEl?.value || "").trim();
    if (!importCode) {
      setStatus("Paste your import code first.", true);
      return;
    }

    setStatus("Importing...");
    await setStorageItem("importCode", importCode);

    const response = await sendRuntimeMessage({
      action: "EXTRACT_ACORN_DATA",
      importCode
    });

    if (!response?.ok) {
      setStatus(response?.error || "Import failed.", true);
      return;
    }

    setStatus(response.message || "Imported successfully");
  } catch (error) {
    setStatus(error instanceof Error ? error.message : String(error), true);
  }
});
