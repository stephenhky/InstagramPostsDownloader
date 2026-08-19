document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const batchForm = document.getElementById("batch-download-form");
    const postRowsContainer = document.getElementById("post-rows-container");
    const addRowBtn = document.getElementById("add-row-btn");
    const submitBtn = document.getElementById("submit-btn");
    const openDownloadsBtn = document.getElementById("open-downloads-btn");
    const postCounter = document.getElementById("post-counter");
    
    // Platform Elements
    const platformBtns = document.querySelectorAll(".platform-btn");
    const logoIg = document.getElementById("logo-icon-instagram");
    const logoTh = document.getElementById("logo-icon-threads");
    
    // Auth Session Elements
    const statusIndicator = document.getElementById("status-indicator");
    const sessionStatusText = document.getElementById("session-status-text");
    const connectBtn = document.getElementById("connect-btn");
    const disconnectBtn = document.getElementById("disconnect-btn");
    const sessionDescText = document.getElementById("session-desc-text");
    const threadsOptionalNotice = document.getElementById("threads-optional-notice");
    
    // Status Elements
    const statusCard = document.getElementById("batch-status-card");
    const statusTitle = document.getElementById("batch-status-title");
    const statusSpinner = document.getElementById("batch-status-spinner");
    const progressBar = document.getElementById("batch-progress-bar");
    const statusMessage = document.getElementById("batch-status-message");
    const resultsList = document.getElementById("batch-results-list");
    
    // Summary Elements
    const summaryCard = document.getElementById("batch-summary");
    const summarySucceeded = document.getElementById("summary-succeeded");
    const summaryFailed = document.getElementById("summary-failed");
    const summaryTotal = document.getElementById("summary-total");

    const MAX_POSTS = 9;
    let rowCount = 0;
    
    let currentPlatform = localStorage.getItem("instadrop_platform") || "instagram";
    let isConnected = false;
    let authPollingInterval = null;

    // Initialize Page
    initPlatform();
    
    // Initial rows
    for (let i = 0; i < 3; i++) {
        addRow();
    }

    // ── Platform Switching ──────────────────────────────────────
    platformBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const platform = btn.dataset.platform;
            if (platform !== currentPlatform) {
                currentPlatform = platform;
                localStorage.setItem("instadrop_platform", currentPlatform);
                initPlatform();
            }
        });
    });

    function initPlatform() {
        platformBtns.forEach(btn => {
            if (btn.dataset.platform === currentPlatform) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });

        document.body.className = `platform-${currentPlatform}`;

        if (currentPlatform === "instagram") {
            logoIg.style.display = "block";
            logoTh.style.display = "none";
            threadsOptionalNotice.style.display = "none";
            document.querySelectorAll(".row-url-input").forEach(input => {
                input.placeholder = "https://www.instagram.com/p/...";
            });
        } else {
            logoIg.style.display = "none";
            logoTh.style.display = "block";
            threadsOptionalNotice.style.display = "flex";
            document.querySelectorAll(".row-url-input").forEach(input => {
                input.placeholder = "https://www.threads.net/@username/post/...";
            });
        }

        statusCard.style.display = "none";
        resultsList.innerHTML = "";
        summaryCard.style.display = "none";
        
        checkAuthStatus();
    }

    // ── Auth Handling ───────────────────────────────────────────
    async function checkAuthStatus() {
        try {
            const response = await fetch(`/api/${currentPlatform}/auth/status`);
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
            sessionStatusText.textContent = `${currentPlatform === 'instagram' ? 'Instagram' : 'Threads'} Session: Connected`;
            sessionDescText.textContent = "Your session is cached locally. Downloads will run silently in the background.";
            connectBtn.style.display = "none";
            disconnectBtn.style.display = "inline-block";
            disconnectBtn.disabled = false;
            
            submitBtn.disabled = false;
            submitBtn.querySelector("span").textContent = "Download All Posts";
        } else {
            statusIndicator.classList.add("disconnected");
            if (currentPlatform === "instagram") {
                sessionStatusText.textContent = "Instagram Session: Disconnected";
                sessionDescText.textContent = "We need an active Instagram session to download posts.";
                connectBtn.style.display = "inline-block";
                connectBtn.querySelector("span").textContent = "Connect Instagram Account";
                submitBtn.disabled = true;
                submitBtn.querySelector("span").textContent = "Connect Account First";
            } else {
                sessionStatusText.textContent = "Threads Session: Not logged in (Optional)";
                sessionDescText.textContent = "Public Threads posts can be downloaded without logging in.";
                connectBtn.style.display = "inline-block";
                connectBtn.querySelector("span").textContent = "Login to Threads (Optional)";
                submitBtn.disabled = false;
                submitBtn.querySelector("span").textContent = "Download All Posts";
            }
            connectBtn.disabled = false;
            disconnectBtn.style.display = "none";
        }
    }

    connectBtn.addEventListener("click", async () => {
        connectBtn.disabled = true;
        connectBtn.querySelector("span").textContent = "Opening Login Window...";
        sessionDescText.innerHTML = `<span style="color: var(--primary-color); font-weight:600;">Action Required:</span> A browser window has opened. Please log in manually inside that window.`;
        
        try {
            fetch(`/api/${currentPlatform}/auth/login`, { method: "POST" })
                .then(res => res.json())
                .catch(err => console.error("Login call failed", err));
            
            if (authPollingInterval) clearInterval(authPollingInterval);
            
            let pollCounter = 0;
            authPollingInterval = setInterval(async () => {
                pollCounter++;
                const authenticated = await checkAuthStatus();
                if (authenticated) {
                    clearInterval(authPollingInterval);
                }
                if (pollCounter > 90) {
                    clearInterval(authPollingInterval);
                    checkAuthStatus();
                }
            }, 2000);
            
        } catch (err) {
            console.error("Failed to start login flow:", err);
            connectBtn.disabled = false;
        }
    });

    disconnectBtn.addEventListener("click", async () => {
        if (!confirm(`Clear your cached ${currentPlatform} session?`)) return;
        disconnectBtn.disabled = true;
        
        try {
            const res = await fetch(`/api/${currentPlatform}/auth/logout`, { method: "POST" });
            const data = await res.json();
            if (data.success) checkAuthStatus();
        } catch (err) {
            console.error("Error disconnecting session:", err);
            disconnectBtn.disabled = false;
        }
    });

    openDownloadsBtn.addEventListener("click", async () => {
        try {
            const res = await fetch(`/api/${currentPlatform}/open-folder`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({})
            });
            const data = await res.json();
            if (!data.success) alert("Could not open folder: " + data.detail);
        } catch (err) {
            console.error(err);
            alert("Error trying to open folder locally.");
        }
    });

    // ── Batch Row Management ────────────────────────────────────
    function updateRowCounters() {
        const rows = document.querySelectorAll(".post-row");
        rows.forEach((row, index) => {
            row.querySelector(".row-number").textContent = index + 1;
        });
        
        postCounter.textContent = `${rowCount} / ${MAX_POSTS}`;
        
        const removeBtns = document.querySelectorAll(".btn-remove-row");
        removeBtns.forEach(btn => {
            btn.disabled = rowCount <= 1;
        });
        
        addRowBtn.disabled = rowCount >= MAX_POSTS;
    }

    function addRow() {
        if (rowCount >= MAX_POSTS) return;
        rowCount++;
        
        const row = document.createElement("div");
        row.className = "post-row";
        
        const placeholder = currentPlatform === "instagram" ? "https://www.instagram.com/p/..." : "https://www.threads.net/@username/post/...";
        
        row.innerHTML = `
            <div class="row-number">${rowCount}</div>
            <input type="url" class="row-url-input" placeholder="${placeholder}" required>
            <input type="text" class="row-suffix-input" placeholder="Suffix (Optional)">
            <button type="button" class="btn-remove-row" title="Remove row">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        `;
        
        const removeBtn = row.querySelector(".btn-remove-row");
        removeBtn.addEventListener("click", () => {
            if (rowCount > 1) {
                row.remove();
                rowCount--;
                updateRowCounters();
            }
        });
        
        // Share link resolution (Threads only)
        const urlInput = row.querySelector(".row-url-input");
        urlInput.addEventListener("blur", async () => {
            if (currentPlatform !== "threads") return;
            const url = urlInput.value.trim();
            if (!url || !url.includes("/share/")) return;
            
            const orig = urlInput.placeholder;
            urlInput.placeholder = "Resolving share link...";
            urlInput.disabled = true;
            try {
                const res = await fetch(`/api/${currentPlatform}/resolve-url`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ url })
                });
                const data = await res.json();
                if (data.success && data.resolved_url !== url) {
                    urlInput.value = data.resolved_url;
                }
            } catch (e) {
                console.error(e);
            } finally {
                urlInput.disabled = false;
                urlInput.placeholder = orig;
            }
        });
        
        postRowsContainer.appendChild(row);
        updateRowCounters();
    }

    addRowBtn.addEventListener("click", addRow);

    // ── Batch Download Execution ─────────────────────────────────
    batchForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        if (currentPlatform === "instagram" && !isConnected) {
            alert("Please connect your Instagram account first.");
            return;
        }

        const rows = document.querySelectorAll(".post-row");
        const itemsToDownload = [];
        
        rows.forEach(row => {
            const url = row.querySelector(".row-url-input").value.trim();
            const suffix = row.querySelector(".row-suffix-input").value.trim();
            if (url) {
                itemsToDownload.push({ url, suffix, rowElement: row });
            }
        });
        
        if (itemsToDownload.length === 0) {
            alert("Please enter at least one URL.");
            return;
        }

        // Setup UI for processing
        statusCard.style.display = "block";
        statusCard.scrollIntoView({ behavior: "smooth" });
        
        statusTitle.textContent = `Batch Processing (${itemsToDownload.length} items)`;
        statusSpinner.style.display = "block";
        progressBar.style.width = "5%";
        progressBar.style.background = "var(--primary-glow)";
        statusMessage.textContent = "Starting batch downloads sequentially. Please wait...";
        
        resultsList.innerHTML = "";
        summaryCard.style.display = "none";
        
        submitBtn.disabled = true;
        submitBtn.querySelector("span").textContent = "Processing Batch...";
        addRowBtn.disabled = true;
        
        let successCount = 0;
        let failCount = 0;
        const total = itemsToDownload.length;
        
        for (let i = 0; i < total; i++) {
            const item = itemsToDownload[i];
            const progressPercent = Math.max(5, Math.floor((i / total) * 100));
            progressBar.style.width = `${progressPercent}%`;
            statusMessage.textContent = `Processing item ${i + 1} of ${total}...`;
            
            // Mark row as processing
            item.rowElement.classList.remove("row-error", "row-success");
            item.rowElement.classList.add("row-processing");
            
            // Add pending result item to list
            const resultItem = document.createElement("div");
            resultItem.className = "batch-result-item result-active";
            resultItem.innerHTML = `
                <div class="result-icon">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="12" y1="2" x2="12" y2="6"></line>
                        <line x1="12" y1="18" x2="12" y2="22"></line>
                        <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line>
                        <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line>
                        <line x1="2" y1="12" x2="6" y2="12"></line>
                        <line x1="18" y1="12" x2="22" y2="12"></line>
                        <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line>
                        <line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line>
                    </svg>
                </div>
                <div class="result-text">
                    <span class="result-url">${item.url}</span>
                    <span class="result-detail">Downloading...</span>
                </div>
            `;
            resultsList.appendChild(resultItem);
            
            try {
                const response = await fetch(`/api/${currentPlatform}/download`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ url: item.url, suffix: item.suffix || null })
                });
                
                const result = await response.json();
                
                item.rowElement.classList.remove("row-processing");
                resultItem.classList.remove("result-active");
                
                if (response.ok && result.success) {
                    successCount++;
                    item.rowElement.classList.add("row-success");
                    resultItem.classList.add("result-success");
                    resultItem.querySelector(".result-icon").innerHTML = `
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                    `;
                    resultItem.querySelector(".result-detail").textContent = `Success: Downloaded ${result.data.media_files.length} file(s) for @${result.data.owner_username}`;
                } else {
                    failCount++;
                    item.rowElement.classList.add("row-error");
                    resultItem.classList.add("result-error");
                    resultItem.querySelector(".result-icon").innerHTML = `
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="18" y1="6" x2="6" y2="18"></line>
                            <line x1="6" y1="6" x2="18" y2="18"></line>
                        </svg>
                    `;
                    resultItem.querySelector(".result-detail").textContent = `Failed: ${result.detail || "Unknown error"}`;
                }
            } catch (err) {
                failCount++;
                item.rowElement.classList.remove("row-processing");
                item.rowElement.classList.add("row-error");
                resultItem.classList.remove("result-active");
                resultItem.classList.add("result-error");
                resultItem.querySelector(".result-icon").innerHTML = `
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                `;
                resultItem.querySelector(".result-detail").textContent = "Failed: Network or Server Error";
            }
        }
        
        // Finalize Batch Processing
        statusSpinner.style.display = "none";
        progressBar.style.width = "100%";
        
        if (failCount === 0) {
            statusTitle.textContent = "Batch Download Complete!";
            progressBar.style.background = "var(--success-color)";
            statusMessage.textContent = `Successfully downloaded all ${total} items.`;
        } else if (successCount === 0) {
            statusTitle.textContent = "Batch Download Failed";
            progressBar.style.background = "var(--error-color)";
            statusMessage.textContent = `All ${total} items failed to download. Check errors below.`;
        } else {
            statusTitle.textContent = "Batch Download Finished with Errors";
            progressBar.style.background = "linear-gradient(90deg, var(--success-color) 50%, var(--error-color) 100%)";
            statusMessage.textContent = `Downloaded ${successCount} items successfully, ${failCount} failed.`;
        }
        
        // Update Summary
        summarySucceeded.textContent = successCount;
        summaryFailed.textContent = failCount;
        summaryTotal.textContent = total;
        summaryCard.style.display = "block";
        
        submitBtn.disabled = false;
        submitBtn.querySelector("span").textContent = "Download All Posts";
        updateRowCounters(); // restores addBtn if not max
    });
});
