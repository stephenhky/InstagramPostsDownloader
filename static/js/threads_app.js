document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const downloadForm = document.getElementById("download-form");
    const postUrlInput = document.getElementById("post-url");
    const filenameSuffixInput = document.getElementById("filename-suffix");
    const submitBtn = document.getElementById("submit-btn");
    const openDownloadsBtn = document.getElementById("open-downloads-btn");

    // Auth Session Elements
    const statusIndicator = document.getElementById("status-indicator");
    const sessionStatusText = document.getElementById("session-status-text");
    const connectBtn = document.getElementById("connect-btn");
    const disconnectBtn = document.getElementById("disconnect-btn");
    const sessionDescText = document.getElementById("session-desc-text");

    // Status Card Elements
    const statusCard = document.getElementById("status-card");
    const statusTitle = document.getElementById("status-title");
    const statusSpinner = document.getElementById("status-spinner");
    const progressBar = document.getElementById("progress-bar");
    const statusMessage = document.getElementById("status-message");
    const resultPreview = document.getElementById("download-result-preview");
    const resultUsername = document.getElementById("result-username");
    const resultCaption = document.getElementById("result-caption");
    const resultMediaCount = document.getElementById("result-media-count");

    // History Elements
    const historyGrid = document.getElementById("history-grid");
    const noHistoryState = document.getElementById("no-history");
    const historyCount = document.getElementById("history-count");

    // State
    let isConnected = false;
    let authPollingInterval = null;

    // Init
    checkAuthStatus();
    loadHistory();

    // ── Auth status ──────────────────────────────────────────────

    async function checkAuthStatus() {
        try {
            const res = await fetch("/api/auth/status");
            const data = await res.json();
            isConnected = data.authenticated;
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
            sessionStatusText.textContent = "Threads Session: Connected";
            sessionDescText.textContent =
                "Your session is cached locally. Downloads will run in the background.";
            connectBtn.style.display = "none";
            disconnectBtn.style.display = "inline-block";
            disconnectBtn.disabled = false;
            disconnectBtn.textContent = "Disconnect Account";
        } else {
            // Login is OPTIONAL for Threads — don't block the download button
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

        // Download is always enabled — login is not required
        submitBtn.disabled = false;
        submitBtn.querySelector("span").textContent = "Download Post";
    }

    // ── Login flow ───────────────────────────────────────────────

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
                const authenticated = await checkAuthStatus();
                if (authenticated) {
                    clearInterval(authPollingInterval);
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

    // ── Download form submission ─────────────────────────────────

    downloadForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const url = postUrlInput.value.trim();
        const suffix = filenameSuffixInput.value.trim();

        statusCard.style.display = "block";
        statusCard.scrollIntoView({ behavior: "smooth" });

        statusTitle.textContent = "Processing Download...";
        statusSpinner.style.display = "block";
        progressBar.style.width = "25%";
        progressBar.style.background = "var(--primary-glow)";
        statusMessage.textContent =
            "Launching background browser and loading the Threads post. Please wait...";
        resultPreview.style.display = "none";

        submitBtn.disabled = true;
        submitBtn.querySelector("span").textContent = "Downloading...";

        try {
            const res = await fetch("/api/download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url, suffix: suffix || null }),
            });
            const result = await res.json();

            if (res.ok && result.success) {
                statusTitle.textContent = "Download Complete!";
                statusSpinner.style.display = "none";
                progressBar.style.width = "100%";
                statusMessage.textContent = "Post downloaded successfully to your local machine.";

                resultUsername.textContent = `@${result.data.owner_username}`;
                resultCaption.textContent = result.data.caption || "No caption";
                resultMediaCount.textContent = `Downloaded ${result.data.media_files.length} media file(s).`;
                resultPreview.style.display = "flex";

                postUrlInput.value = "";
                filenameSuffixInput.value = "";
                loadHistory();
            } else {
                showError(result.detail || "Unknown error occurred.");
            }
        } catch (err) {
            showError("Network error. Make sure the backend server is running.");
        } finally {
            submitBtn.disabled = false;
            submitBtn.querySelector("span").textContent = "Download Post";
        }
    });

    function showError(message) {
        statusTitle.textContent = "Download Failed";
        statusSpinner.style.display = "none";
        progressBar.style.width = "100%";
        progressBar.style.background = "var(--error-color)";
        statusMessage.innerHTML =
            `<span style="color:var(--error-color);font-weight:600;">Error:</span> ${message}`;
        resultPreview.style.display = "none";
    }

    // ── History ──────────────────────────────────────────────────

    async function loadHistory() {
        try {
            const res = await fetch("/api/history");
            const result = await res.json();

            const existing = historyGrid.querySelectorAll(".history-card");
            existing.forEach(c => c.remove());

            if (res.ok && result.history.length > 0) {
                noHistoryState.style.display = "none";
                historyCount.textContent = `${result.history.length} items`;
                result.history.forEach(post => historyGrid.appendChild(createHistoryCard(post)));
                initCarousels();
            } else {
                noHistoryState.style.display = "flex";
                historyCount.textContent = "0 items";
            }
        } catch (err) {
            console.error("Failed to load history:", err);
        }
    }

    function createHistoryCard(post) {
        const card = document.createElement("article");
        card.className = "history-card";
        card.dataset.postId = post.post_id;

        const filesCount = post.media_files.length;
        let mediaHtml = "";

        if (filesCount > 1) {
            mediaHtml += `<span class="card-media-badge">${filesCount} slides</span>`;
            mediaHtml += `
                <button type="button" class="carousel-btn carousel-btn-prev">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="15 18 9 12 15 6"></polyline>
                    </svg>
                </button>
                <button type="button" class="carousel-btn carousel-btn-next">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="9 18 15 12 9 6"></polyline>
                    </svg>
                </button>`;
        }

        if (post.is_video && filesCount === 1) {
            mediaHtml += `
                <div class="video-badge">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                        <polygon points="5 3 19 12 5 21 5 3"></polygon>
                    </svg>
                </div>`;
        }

        let slidesHtml = "";
        post.media_files.forEach((filename, idx) => {
            const isVid = filename.toLowerCase().endsWith(".mp4");
            const src = `/downloads_threads/${post.post_id}/${filename}`;
            const active = idx === 0 ? "active" : "";
            if (isVid) {
                slidesHtml += `
                    <div class="slide ${active}" data-index="${idx}">
                        <video src="${src}" controls loop muted playsinline preload="metadata"></video>
                    </div>`;
            } else {
                slidesHtml += `
                    <div class="slide ${active}" data-index="${idx}">
                        <img src="${src}" alt="Threads post item" loading="lazy">
                    </div>`;
            }
        });

        let dotsHtml = "";
        if (filesCount > 1) {
            dotsHtml = '<div class="carousel-dots">';
            post.media_files.forEach((_, idx) => {
                dotsHtml += `<span class="carousel-dot ${idx === 0 ? "active" : ""}" data-index="${idx}"></span>`;
            });
            dotsHtml += "</div>";
        }

        const cleanCaption = post.caption ? escapeHTML(post.caption) : "No caption";
        const cleanDate = formatDate(post.downloaded_at);

        card.innerHTML = `
            <div class="card-media-container">
                ${mediaHtml}${slidesHtml}${dotsHtml}
            </div>
            <div class="card-details">
                <div class="card-author-row">
                    <a href="https://www.threads.net/@${post.owner_username}" target="_blank" rel="noopener" class="author-link">@${post.owner_username}</a>
                    <span class="download-date">${cleanDate}</span>
                </div>
                <p class="card-caption" title="${cleanCaption}">${cleanCaption}</p>
                <div class="card-actions">
                    <a href="${post.url}" target="_blank" rel="noopener" class="card-btn card-btn-view">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                            <polyline points="15 3 21 3 21 9"></polyline>
                            <line x1="10" y1="14" x2="21" y2="3"></line>
                        </svg>
                        <span>Threads</span>
                    </a>
                    <button type="button" class="card-btn card-btn-folder btn-open-card-folder" data-post-id="${post.post_id}">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                        </svg>
                        <span>Open Folder</span>
                    </button>
                </div>
            </div>`;

        card.querySelector(".btn-open-card-folder").addEventListener("click", async () => {
            try {
                await fetch("/api/open-folder", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ post_id: post.post_id }),
                });
            } catch (err) {
                console.error("Failed to open folder:", err);
            }
        });

        return card;
    }

    function initCarousels() {
        document.querySelectorAll(".card-media-container").forEach(container => {
            const slides = container.querySelectorAll(".slide");
            if (slides.length <= 1) return;

            const btnPrev = container.querySelector(".carousel-btn-prev");
            const btnNext = container.querySelector(".carousel-btn-next");
            const dots = container.querySelectorAll(".carousel-dot");
            let current = 0;

            function showSlide(index) {
                const curVid = slides[current].querySelector("video");
                if (curVid) curVid.pause();
                slides[current].classList.remove("active");
                if (dots[current]) dots[current].classList.remove("active");

                current = (index + slides.length) % slides.length;
                slides[current].classList.add("active");
                if (dots[current]) dots[current].classList.add("active");

                const nextVid = slides[current].querySelector("video");
                if (nextVid) nextVid.play().catch(() => {});
            }

            btnPrev.addEventListener("click", e => { e.stopPropagation(); showSlide(current - 1); });
            btnNext.addEventListener("click", e => { e.stopPropagation(); showSlide(current + 1); });
            dots.forEach((dot, idx) => {
                dot.addEventListener("click", e => { e.stopPropagation(); showSlide(idx); });
            });
        });
    }

    function escapeHTML(str) {
        return str.replace(/[&<>'"]/g, t => (
            { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[t] || t
        ));
    }

    function formatDate(dateStr) {
        try {
            return new Date(dateStr).toLocaleDateString("en-US", {
                month: "short", day: "numeric", year: "numeric",
            });
        } catch { return dateStr; }
    }
});
