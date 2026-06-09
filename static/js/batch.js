document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const batchForm = document.getElementById("batch-download-form");
    const postRowsContainer = document.getElementById("post-rows-container");
    const addRowBtn = document.getElementById("add-row-btn");
    const submitBtn = document.getElementById("submit-btn");
    const openDownloadsBtn = document.getElementById("open-downloads-btn");
    const postCounter = document.getElementById("post-counter");

    // Auth Session Elements
    const statusIndicator = document.getElementById("status-indicator");
    const sessionStatusText = document.getElementById("session-status-text");
    const connectBtn = document.getElementById("connect-btn");
    const disconnectBtn = document.getElementById("disconnect-btn");
    const sessionDescText = document.getElementById("session-desc-text");

    // Batch Status Elements
    const batchStatusCard = document.getElementById("batch-status-card");
    const batchStatusTitle = document.getElementById("batch-status-title");
    const batchStatusSpinner = document.getElementById("batch-status-spinner");
    const batchProgressBar = document.getElementById("batch-progress-bar");
    const batchStatusMessage = document.getElementById("batch-status-message");
    const batchResultsList = document.getElementById("batch-results-list");
    const batchSummary = document.getElementById("batch-summary");
    const summarySucceeded = document.getElementById("summary-succeeded");
    const summaryFailed = document.getElementById("summary-failed");
    const summaryTotal = document.getElementById("summary-total");

    // Constants
    const MAX_ROWS = 9;
    const INITIAL_ROWS = 3;

    // State
    let isConnected = false;
    let authPollingInterval = null;
    let rowCount = 0;

    // Initialize
    checkAuthStatus();
    for (let i = 0; i < INITIAL_ROWS; i++) {
        addPostRow();
    }

    // ─────────────────────────────────────────────
    // Auth Management (mirrors app.js behaviour)
    // ─────────────────────────────────────────────

    async function checkAuthStatus() {
        try {
            const response = await fetch("/api/auth/status");
            const result = await response.json();
            isConnected = result.authenticated;
            updateAuthUI(isConnected);
            return isConnected;
        } catch (err) {
            console.error("Error checking auth status:", err);
            updateAuthUI(false);
            return false;
        }
    }

    function updateAuthUI(connected) {
        statusIndicator.className = "status-indicator-dot";

        if (connected) {
            statusIndicator.classList.add("connected");
            sessionStatusText.textContent = "Instagram Session: Connected";
            sessionDescText.textContent = "Your session is cached locally. Downloads will run silently in the background.";
            connectBtn.style.display = "none";
            disconnectBtn.style.display = "inline-block";
            disconnectBtn.disabled = false;
            disconnectBtn.textContent = "Disconnect Account";
            submitBtn.disabled = false;
            submitBtn.querySelector("span").textContent = "Download All Posts";
        } else {
            statusIndicator.classList.add("disconnected");
            sessionStatusText.textContent = "Instagram Session: Disconnected";
            sessionDescText.textContent = "We need an active Instagram session to download posts. Click below to connect.";
            connectBtn.style.display = "inline-block";
            connectBtn.disabled = false;
            connectBtn.querySelector("span").textContent = "Connect Instagram Account";
            disconnectBtn.style.display = "none";
            submitBtn.disabled = true;
            submitBtn.querySelector("span").textContent = "Connect Account First";
        }
    }

    connectBtn.addEventListener("click", async () => {
        connectBtn.disabled = true;
        connectBtn.querySelector("span").textContent = "Opening Login Window...";
        sessionDescText.innerHTML = `<span style="color: var(--primary-color); font-weight:600;">Action Required:</span> A browser window has opened. Please log in manually inside that window. We will automatically detect when you're done.`;

        try {
            fetch("/api/auth/login", { method: "POST" })
                .then(res => res.json())
                .then(data => console.info("Login flow process returned:", data))
                .catch(err => console.error("Login call failed", err));

            if (authPollingInterval) clearInterval(authPollingInterval);
            let pollCounter = 0;
            authPollingInterval = setInterval(async () => {
                pollCounter++;
                const authenticated = await checkAuthStatus();
                if (authenticated) {
                    clearInterval(authPollingInterval);
                    connectBtn.querySelector("span").textContent = "Connect Instagram Account";
                }
                if (pollCounter > 90) {
                    clearInterval(authPollingInterval);
                    checkAuthStatus();
                    alert("Login session setup timed out. Please try again.");
                }
            }, 2000);
        } catch (err) {
            console.error("Failed to start login flow:", err);
            connectBtn.disabled = false;
            connectBtn.querySelector("span").textContent = "Connect Instagram Account";
            sessionDescText.textContent = "Failed to launch browser login window. Please make sure the app backend is running.";
        }
    });

    disconnectBtn.addEventListener("click", async () => {
        if (!confirm("Are you sure you want to log out and clear your cached session?")) return;
        disconnectBtn.disabled = true;
        disconnectBtn.textContent = "Disconnecting...";
        try {
            const res = await fetch("/api/auth/logout", { method: "POST" });
            const data = await res.json();
            if (data.success) {
                checkAuthStatus();
            } else {
                alert("Failed to logout session.");
                disconnectBtn.disabled = false;
                disconnectBtn.textContent = "Disconnect Account";
            }
        } catch (err) {
            console.error("Error disconnecting session:", err);
            disconnectBtn.disabled = false;
            disconnectBtn.textContent = "Disconnect Account";
        }
    });

    // ─────────────────────────────────────────────
    // Post Row Management
    // ─────────────────────────────────────────────

    function addPostRow() {
        if (rowCount >= MAX_ROWS) return;
        rowCount++;

        const rowId = rowCount;
        const row = document.createElement("div");
        row.className = "post-row";
        row.dataset.rowId = rowId;

        row.innerHTML = `
            <div class="row-number">${rowId}</div>
            <input type="url" class="row-url-input" placeholder="https://www.instagram.com/p/..." data-field="url">
            <input type="text" class="row-suffix-input" placeholder="Suffix (optional)" data-field="suffix">
            <button type="button" class="btn-remove-row" title="Remove this row">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        `;

        // Remove row handler
        const removeBtn = row.querySelector(".btn-remove-row");
        removeBtn.addEventListener("click", () => {
            row.style.animation = "slideOut 0.25s cubic-bezier(0.4, 0, 0.2, 1) forwards";
            row.addEventListener("animationend", () => {
                row.remove();
                rowCount--;
                renumberRows();
                updatePostCounter();
                updateAddButtonState();
            }, { once: true });
        });

        postRowsContainer.appendChild(row);
        updatePostCounter();
        updateAddButtonState();

        // Focus on new row URL input
        const urlInput = row.querySelector(".row-url-input");
        urlInput.focus();
    }

    function renumberRows() {
        const rows = postRowsContainer.querySelectorAll(".post-row");
        rows.forEach((row, idx) => {
            row.querySelector(".row-number").textContent = idx + 1;
            row.dataset.rowId = idx + 1;
        });
    }

    function updatePostCounter() {
        const rows = postRowsContainer.querySelectorAll(".post-row");
        postCounter.textContent = `${rows.length} / ${MAX_ROWS}`;
    }

    function updateAddButtonState() {
        const rows = postRowsContainer.querySelectorAll(".post-row");
        addRowBtn.disabled = rows.length >= MAX_ROWS;
    }

    // Add CSS animation for slide-out
    const styleSheet = document.createElement("style");
    styleSheet.textContent = `
        @keyframes slideOut {
            from { opacity: 1; transform: translateY(0); height: auto; }
            to { opacity: 0; transform: translateY(-8px); height: 0; padding: 0; margin: 0; overflow: hidden; }
        }
    `;
    document.head.appendChild(styleSheet);

    addRowBtn.addEventListener("click", () => {
        addPostRow();
    });

    // ─────────────────────────────────────────────
    // Open Downloads Folder
    // ─────────────────────────────────────────────

    openDownloadsBtn.addEventListener("click", async () => {
        try {
            const res = await fetch("/api/open-folder", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({})
            });
            const data = await res.json();
            if (!data.success) {
                alert("Could not open folder: " + data.detail);
            }
        } catch (err) {
            console.error(err);
            alert("Error trying to open folder locally.");
        }
    });

    // ─────────────────────────────────────────────
    // Batch Form Submission
    // ─────────────────────────────────────────────

    batchForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        if (!isConnected) {
            alert("Please connect your Instagram account first.");
            return;
        }

        // Collect rows with non-empty URLs
        const rows = postRowsContainer.querySelectorAll(".post-row");
        const items = [];
        const rowElements = [];

        rows.forEach(row => {
            const url = row.querySelector('[data-field="url"]').value.trim();
            const suffix = row.querySelector('[data-field="suffix"]').value.trim();

            if (url) {
                items.push({ url, suffix: suffix || null });
                rowElements.push(row);
            }
        });

        if (items.length === 0) {
            alert("Please enter at least one Instagram post URL.");
            return;
        }

        // Show status card
        batchStatusCard.style.display = "block";
        batchStatusCard.scrollIntoView({ behavior: "smooth" });

        // Reset status UI
        batchStatusTitle.textContent = `Processing ${items.length} Post${items.length > 1 ? "s" : ""}...`;
        batchStatusSpinner.style.display = "block";
        batchProgressBar.style.width = "5%";
        batchProgressBar.style.background = "var(--primary-glow)";
        batchProgressBar.style.animation = "none";
        batchStatusMessage.textContent = `Starting batch download of ${items.length} post${items.length > 1 ? "s" : ""}. This may take a while...`;
        batchResultsList.innerHTML = "";
        batchSummary.style.display = "none";

        // Build initial result items (pending state)
        items.forEach((item, idx) => {
            const resultItem = createResultItem(idx, item.url, "pending", "Waiting...");
            batchResultsList.appendChild(resultItem);
        });

        // Disable controls
        submitBtn.disabled = true;
        submitBtn.querySelector("span").textContent = "Downloading...";
        setRowsDisabled(true);

        try {
            const response = await fetch("/api/batch-download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ items })
            });

            const result = await response.json();

            if (response.ok) {
                // Update each result item
                batchResultsList.innerHTML = "";
                result.results.forEach((r, idx) => {
                    const row = rowElements[idx];

                    if (r.success) {
                        const detail = `@${r.data.owner_username} — ${r.data.media_files.length} file${r.data.media_files.length > 1 ? "s" : ""}`;
                        const resultItem = createResultItem(idx, r.url, "success", detail);
                        batchResultsList.appendChild(resultItem);
                        if (row) {
                            row.classList.remove("row-processing", "row-error");
                            row.classList.add("row-success");
                        }
                    } else {
                        const resultItem = createResultItem(idx, r.url, "error", r.error || "Unknown error");
                        batchResultsList.appendChild(resultItem);
                        if (row) {
                            row.classList.remove("row-processing", "row-success");
                            row.classList.add("row-error");
                        }
                    }
                });

                // Update progress bar
                batchProgressBar.style.width = "100%";
                batchProgressBar.style.background = result.failed > 0
                    ? "linear-gradient(135deg, var(--success-color) 0%, var(--error-color) 100%)"
                    : "var(--success-color)";

                // Update title
                if (result.failed === 0) {
                    batchStatusTitle.textContent = "All Downloads Complete!";
                    batchStatusMessage.textContent = `Successfully downloaded ${result.succeeded} post${result.succeeded > 1 ? "s" : ""}.`;
                } else {
                    batchStatusTitle.textContent = "Batch Download Finished";
                    batchStatusMessage.textContent = `${result.succeeded} succeeded, ${result.failed} failed out of ${result.total} total.`;
                }

                batchStatusSpinner.style.display = "none";

                // Show summary
                summarySucceeded.textContent = result.succeeded;
                summaryFailed.textContent = result.failed;
                summaryTotal.textContent = result.total;
                batchSummary.style.display = "block";

            } else {
                const errDetail = result.detail || "Unknown error occurred.";
                batchStatusTitle.textContent = "Batch Download Failed";
                batchStatusSpinner.style.display = "none";
                batchProgressBar.style.width = "100%";
                batchProgressBar.style.background = "var(--error-color)";
                batchStatusMessage.innerHTML = `<span style="color: var(--error-color); font-weight: 600;">Error:</span> ${errDetail}`;
            }

        } catch (err) {
            console.error("Batch download error:", err);
            batchStatusTitle.textContent = "Batch Download Failed";
            batchStatusSpinner.style.display = "none";
            batchProgressBar.style.width = "100%";
            batchProgressBar.style.background = "var(--error-color)";
            batchStatusMessage.innerHTML = `<span style="color: var(--error-color); font-weight: 600;">Error:</span> Network error. Make sure the backend server is running.`;
        } finally {
            submitBtn.disabled = false;
            submitBtn.querySelector("span").textContent = "Download All Posts";
            setRowsDisabled(false);
        }
    });

    // ─────────────────────────────────────────────
    // Helpers
    // ─────────────────────────────────────────────

    function createResultItem(index, url, status, detail) {
        const item = document.createElement("div");
        item.className = `batch-result-item result-${status}`;
        item.dataset.index = index;

        let iconSvg = "";
        if (status === "success") {
            iconSvg = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
        } else if (status === "error") {
            iconSvg = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
        } else if (status === "active") {
            iconSvg = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle></svg>`;
        } else {
            iconSvg = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="1"></circle></svg>`;
        }

        // Truncate the URL for display
        let displayUrl = url;
        try {
            const parsed = new URL(url);
            displayUrl = parsed.pathname.replace(/\/$/, "");
        } catch (e) {
            // Use as-is
        }

        item.innerHTML = `
            <div class="result-icon">${iconSvg}</div>
            <div class="result-text">
                <span class="result-url" title="${escapeHTML(url)}">${escapeHTML(displayUrl)}</span>
                <span class="result-detail">${escapeHTML(detail)}</span>
            </div>
        `;

        return item;
    }

    function setRowsDisabled(disabled) {
        const rows = postRowsContainer.querySelectorAll(".post-row");
        rows.forEach(row => {
            row.querySelectorAll("input").forEach(input => {
                input.disabled = disabled;
            });
            const removeBtn = row.querySelector(".btn-remove-row");
            if (removeBtn) removeBtn.disabled = disabled;
        });
        addRowBtn.disabled = disabled || rows.length >= MAX_ROWS;
    }

    function escapeHTML(str) {
        return str.replace(/[&<>'"]/g,
            tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
        );
    }
});
