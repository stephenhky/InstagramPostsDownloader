document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const batchForm = document.getElementById("batch-download-form");
    const postRowsContainer = document.getElementById("post-rows-container");
    const addRowBtn = document.getElementById("add-row-btn");
    const submitBtn = document.getElementById("submit-btn");
    const openDownloadsBtn = document.getElementById("open-downloads-btn");
    const postCounter = document.getElementById("post-counter");

    // Auth Elements
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

    const MAX_ROWS = 9;
    const INITIAL_ROWS = 3;

    let authPollingInterval = null;
    let rowCount = 0;

    // Init
    checkAuthStatus();
    for (let i = 0; i < INITIAL_ROWS; i++) addPostRow();

    // ── Auth ─────────────────────────────────────────────────────

    async function checkAuthStatus() {
        try {
            const res = await fetch("/api/auth/status");
            const data = await res.json();
            updateAuthUI(data.authenticated);
            return data.authenticated;
        } catch (err) {
            console.error("Auth status error:", err);
            updateAuthUI(false);
            return false;
        }
    }

    function updateAuthUI(connected) {
        statusIndicator.className = "status-indicator-dot";

        if (connected) {
            statusIndicator.classList.add("connected");
            sessionStatusText.textContent = "Threads Session: Connected";
            sessionDescText.textContent =
                "Your session is cached locally. Downloads will run in the background.";
            connectBtn.style.display = "none";
            disconnectBtn.style.display = "inline-block";
            disconnectBtn.disabled = false;
            disconnectBtn.textContent = "Disconnect Account";
        } else {
            statusIndicator.classList.add("disconnected");
            sessionStatusText.textContent = "Threads Session: Not logged in (Optional)";
            sessionDescText.textContent =
                "Public Threads posts can be downloaded without logging in. " +
                "Login is optional — it may help with private accounts or rate limits.";
            connectBtn.style.display = "inline-block";
            connectBtn.disabled = false;
            connectBtn.querySelector("span").textContent = "Login to Threads (Optional)";
            disconnectBtn.style.display = "none";
        }

        // Downloads are always enabled — login is not required
        submitBtn.disabled = false;
        submitBtn.querySelector("span").textContent = "Download All Posts";
    }

    connectBtn.addEventListener("click", async () => {
        connectBtn.disabled = true;
        connectBtn.querySelector("span").textContent = "Opening Login Window...";
        sessionDescText.innerHTML =
            `<span style="color:var(--primary-color);font-weight:600;">Action Required:</span> ` +
            `A browser window has opened. Log in to Threads inside that window, ` +
            `then <strong>close the browser window</strong> when you are done. ` +
            `The app will update automatically.`;

        try {
            fetch("/api/auth/login", { method: "POST" })
                .then(r => r.json())
                .catch(err => console.error("Login call failed", err));

            if (authPollingInterval) clearInterval(authPollingInterval);
            let polls = 0;
            authPollingInterval = setInterval(async () => {
                polls++;
                const ok = await checkAuthStatus();
                if (ok) {
                    clearInterval(authPollingInterval);
                    connectBtn.querySelector("span").textContent = "Login to Threads (Optional)";
                }
                if (polls > 90) {
                    clearInterval(authPollingInterval);
                    checkAuthStatus();
                    alert("Login timed out. Please try again.");
                }
            }, 2000);
        } catch (err) {
            console.error("Failed to start login flow:", err);
            connectBtn.disabled = false;
            connectBtn.querySelector("span").textContent = "Login to Threads (Optional)";
        }
    });

    disconnectBtn.addEventListener("click", async () => {
        if (!confirm("Clear your saved Threads session?")) return;
        disconnectBtn.disabled = true;
        disconnectBtn.textContent = "Disconnecting...";
        try {
            const res = await fetch("/api/auth/logout", { method: "POST" });
            const data = await res.json();
            if (data.success) {
                checkAuthStatus();
            } else {
                alert("Failed to clear session.");
                disconnectBtn.disabled = false;
                disconnectBtn.textContent = "Disconnect Account";
            }
        } catch (err) {
            console.error("Error disconnecting:", err);
            disconnectBtn.disabled = false;
            disconnectBtn.textContent = "Disconnect Account";
        }
    });

    // ── Post row management ──────────────────────────────────────

    function addPostRow() {
        if (rowCount >= MAX_ROWS) return;
        rowCount++;
        const rowId = rowCount;
        const row = document.createElement("div");
        row.className = "post-row";
        row.dataset.rowId = rowId;
        row.innerHTML = `
            <div class="row-number">${rowId}</div>
            <input type="url" class="row-url-input" placeholder="https://www.threads.net/@user/post/..." data-field="url">
            <input type="text" class="row-suffix-input" placeholder="Suffix (optional)" data-field="suffix">
            <button type="button" class="btn-remove-row" title="Remove">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>`;

        row.querySelector(".btn-remove-row").addEventListener("click", () => {
            row.style.animation = "slideOut 0.25s cubic-bezier(0.4,0,0.2,1) forwards";
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
        row.querySelector(".row-url-input").focus();
    }

    function renumberRows() {
        postRowsContainer.querySelectorAll(".post-row").forEach((row, idx) => {
            row.querySelector(".row-number").textContent = idx + 1;
            row.dataset.rowId = idx + 1;
        });
    }
    function updatePostCounter() {
        const count = postRowsContainer.querySelectorAll(".post-row").length;
        postCounter.textContent = `${count} / ${MAX_ROWS}`;
    }
    function updateAddButtonState() {
        addRowBtn.disabled = postRowsContainer.querySelectorAll(".post-row").length >= MAX_ROWS;
    }

    // Slide-out animation
    const styleEl = document.createElement("style");
    styleEl.textContent = `
        @keyframes slideOut {
            from { opacity:1; transform:translateY(0); height:auto; }
            to { opacity:0; transform:translateY(-8px); height:0; padding:0; margin:0; overflow:hidden; }
        }`;
    document.head.appendChild(styleEl);

    addRowBtn.addEventListener("click", addPostRow);

    // ── Open downloads folder ────────────────────────────────────

    openDownloadsBtn.addEventListener("click", async () => {
        try {
            const res = await fetch("/api/open-folder", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({}),
            });
            const data = await res.json();
            if (!data.success) alert("Could not open folder: " + data.detail);
        } catch (err) {
            console.error(err);
            alert("Error opening folder.");
        }
    });

    // ── Batch form submission ────────────────────────────────────

    batchForm.addEventListener("submit", async (e) => {
        e.preventDefault();

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
            alert("Please enter at least one Threads post URL.");
            return;
        }

        batchStatusCard.style.display = "block";
        batchStatusCard.scrollIntoView({ behavior: "smooth" });

        batchStatusTitle.textContent = `Processing ${items.length} Post${items.length > 1 ? "s" : ""}...`;
        batchStatusSpinner.style.display = "block";
        batchProgressBar.style.width = "5%";
        batchProgressBar.style.background = "var(--primary-glow)";
        batchProgressBar.style.animation = "none";
        batchStatusMessage.textContent = `Starting batch download of ${items.length} post${items.length > 1 ? "s" : ""}...`;
        batchResultsList.innerHTML = "";
        batchSummary.style.display = "none";

        items.forEach((item, idx) => {
            batchResultsList.appendChild(createResultItem(idx, item.url, "pending", "Waiting..."));
        });

        submitBtn.disabled = true;
        submitBtn.querySelector("span").textContent = "Downloading...";
        setRowsDisabled(true);

        try {
            const res = await fetch("/api/batch-download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ items }),
            });
            const result = await res.json();

            if (res.ok) {
                batchResultsList.innerHTML = "";
                result.results.forEach((r, idx) => {
                    if (r.success) {
                        const detail = `@${r.data.owner_username} — ${r.data.media_files.length} file${r.data.media_files.length > 1 ? "s" : ""}`;
                        batchResultsList.appendChild(createResultItem(idx, r.url, "success", detail));
                        if (rowElements[idx]) {
                            rowElements[idx].classList.remove("row-processing", "row-error");
                            rowElements[idx].classList.add("row-success");
                        }
                    } else {
                        batchResultsList.appendChild(createResultItem(idx, r.url, "error", r.error || "Unknown error"));
                        if (rowElements[idx]) {
                            rowElements[idx].classList.remove("row-processing", "row-success");
                            rowElements[idx].classList.add("row-error");
                        }
                    }
                });

                batchProgressBar.style.width = "100%";
                batchProgressBar.style.background = result.failed > 0
                    ? "linear-gradient(135deg, var(--success-color) 0%, var(--error-color) 100%)"
                    : "var(--success-color)";

                if (result.failed === 0) {
                    batchStatusTitle.textContent = "All Downloads Complete!";
                    batchStatusMessage.textContent = `Successfully downloaded ${result.succeeded} post${result.succeeded > 1 ? "s" : ""}.`;
                } else {
                    batchStatusTitle.textContent = "Batch Download Finished";
                    batchStatusMessage.textContent = `${result.succeeded} succeeded, ${result.failed} failed out of ${result.total} total.`;
                }
                batchStatusSpinner.style.display = "none";
                summarySucceeded.textContent = result.succeeded;
                summaryFailed.textContent = result.failed;
                summaryTotal.textContent = result.total;
                batchSummary.style.display = "block";
            } else {
                const errDetail = result.detail || "Unknown error.";
                batchStatusTitle.textContent = "Batch Download Failed";
                batchStatusSpinner.style.display = "none";
                batchProgressBar.style.width = "100%";
                batchProgressBar.style.background = "var(--error-color)";
                batchStatusMessage.innerHTML =
                    `<span style="color:var(--error-color);font-weight:600;">Error:</span> ${errDetail}`;
            }
        } catch (err) {
            console.error("Batch error:", err);
            batchStatusTitle.textContent = "Batch Download Failed";
            batchStatusSpinner.style.display = "none";
            batchProgressBar.style.width = "100%";
            batchProgressBar.style.background = "var(--error-color)";
            batchStatusMessage.innerHTML =
                `<span style="color:var(--error-color);font-weight:600;">Error:</span> Network error. Make sure the backend is running.`;
        } finally {
            submitBtn.disabled = false;
            submitBtn.querySelector("span").textContent = "Download All Posts";
            setRowsDisabled(false);
        }
    });

    // ── Helpers ──────────────────────────────────────────────────

    function createResultItem(index, url, status, detail) {
        const item = document.createElement("div");
        item.className = `batch-result-item result-${status}`;
        item.dataset.index = index;

        const icons = {
            success: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
            error: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`,
            active: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle></svg>`,
            pending: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="1"></circle></svg>`,
        };

        let displayUrl = url;
        try {
            const parsed = new URL(url);
            displayUrl = parsed.pathname.replace(/\/$/, "");
        } catch { /* keep as-is */ }

        item.innerHTML = `
            <div class="result-icon">${icons[status] || icons.pending}</div>
            <div class="result-text">
                <span class="result-url" title="${escapeHTML(url)}">${escapeHTML(displayUrl)}</span>
                <span class="result-detail">${escapeHTML(detail)}</span>
            </div>`;
        return item;
    }

    function setRowsDisabled(disabled) {
        postRowsContainer.querySelectorAll(".post-row").forEach(row => {
            row.querySelectorAll("input").forEach(input => { input.disabled = disabled; });
            const btn = row.querySelector(".btn-remove-row");
            if (btn) btn.disabled = disabled;
        });
        addRowBtn.disabled = disabled || postRowsContainer.querySelectorAll(".post-row").length >= MAX_ROWS;
    }

    function escapeHTML(str) {
        return str.replace(/[&<>'"]/g, t => (
            { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[t] || t
        ));
    }
});
