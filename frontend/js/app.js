document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const downloadForm = document.getElementById("download-form");
    const postUrlInput = document.getElementById("post-url");
    const postUrlLabel = document.getElementById("post-url-label");
    const filenameSuffixInput = document.getElementById("filename-suffix");
    const submitBtn = document.getElementById("submit-btn");
    const openDownloadsBtn = document.getElementById("open-downloads-btn");
    
    // Platform Elements
    const platformBtns = document.querySelectorAll(".platform-btn");
    const logoIg = document.getElementById("logo-icon-instagram");
    const logoTh = document.getElementById("logo-icon-threads");
    const appTagline = document.getElementById("app-tagline");
    
    // Auth Session Manager Elements
    const statusIndicator = document.getElementById("status-indicator");
    const sessionStatusText = document.getElementById("session-status-text");
    const connectBtn = document.getElementById("connect-btn");
    const disconnectBtn = document.getElementById("disconnect-btn");
    const sessionDescText = document.getElementById("session-desc-text");
    const threadsOptionalNotice = document.getElementById("threads-optional-notice");
    
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
    const emptyIconIg = document.getElementById("empty-icon-ig");
    const emptyIconTh = document.getElementById("empty-icon-th");
    const noHistoryText = document.getElementById("no-history-text");

    // State Variables
    let currentPlatform = localStorage.getItem("instadrop_platform") || "instagram";
    let isConnected = false;
    let authPollingInterval = null;

    // Initialize Page
    initPlatform();

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
        // Update Buttons
        platformBtns.forEach(btn => {
            if (btn.dataset.platform === currentPlatform) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });

        // Update Body Theme
        document.body.className = `platform-${currentPlatform}`;

        // Update UI Text & Icons
        if (currentPlatform === "instagram") {
            logoIg.style.display = "block";
            logoTh.style.display = "none";
            appTagline.textContent = "Download posts, videos, and slide carousels locally.";
            postUrlLabel.textContent = "Instagram Post / Reel URL";
            postUrlInput.placeholder = "https://www.instagram.com/p/...";
            emptyIconIg.style.display = "block";
            emptyIconTh.style.display = "none";
            noHistoryText.textContent = "No downloads yet. Enter a post URL above to get started!";
            threadsOptionalNotice.style.display = "none";
        } else {
            logoIg.style.display = "none";
            logoTh.style.display = "block";
            appTagline.textContent = "Download Threads posts, images, and videos locally.";
            postUrlLabel.textContent = "Threads Post URL";
            postUrlInput.placeholder = "https://www.threads.net/@username/post/...";
            emptyIconIg.style.display = "none";
            emptyIconTh.style.display = "block";
            noHistoryText.textContent = "No downloads yet. Enter a Threads post URL above to get started!";
            threadsOptionalNotice.style.display = "flex";
        }

        // Reset forms & states
        statusCard.style.display = "none";
        postUrlInput.value = "";
        filenameSuffixInput.value = "";

        // Reload Auth and History
        checkAuthStatus();
        loadHistory();
    }

    // ── Resolve share URLs on blur (Threads) ────────────────────
    postUrlInput.addEventListener("blur", async () => {
        if (currentPlatform !== "threads") return;
        
        const url = postUrlInput.value.trim();
        if (!url || !url.includes("/share/")) return;

        const originalPlaceholder = postUrlInput.placeholder;
        postUrlInput.placeholder = "Resolving share link...";
        postUrlInput.disabled = true;

        try {
            const res = await fetch(`/api/${currentPlatform}/resolve-url`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url }),
            });
            const data = await res.json();
            if (data.success && data.resolved_url !== url) {
                postUrlInput.value = data.resolved_url;
            }
        } catch (err) {
            console.error("Failed to resolve share URL:", err);
        } finally {
            postUrlInput.disabled = false;
            postUrlInput.placeholder = originalPlaceholder;
        }
    });

    // ── Auth Session Manager ────────────────────────────────────
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
            disconnectBtn.textContent = "Disconnect Account";
            
            submitBtn.disabled = false;
            submitBtn.querySelector("span").textContent = "Download Post";
        } else {
            statusIndicator.classList.add("disconnected");
            if (currentPlatform === "instagram") {
                sessionStatusText.textContent = "Instagram Session: Disconnected";
                sessionDescText.textContent = "We need an active Instagram session to download posts. Click below to connect.";
                connectBtn.style.display = "inline-block";
                connectBtn.querySelector("span").textContent = "Connect Instagram Account";
                submitBtn.disabled = true;
                submitBtn.querySelector("span").textContent = "Connect Account First";
            } else {
                sessionStatusText.textContent = "Threads Session: Not logged in (Optional)";
                sessionDescText.textContent = "Public Threads posts can be downloaded without logging in. Login is optional — it may help with private accounts or rate limits.";
                connectBtn.style.display = "inline-block";
                connectBtn.querySelector("span").textContent = "Login to Threads (Optional)";
                submitBtn.disabled = false;
                submitBtn.querySelector("span").textContent = "Download Post";
            }
            connectBtn.disabled = false;
            disconnectBtn.style.display = "none";
        }
    }

    connectBtn.addEventListener("click", async () => {
        connectBtn.disabled = true;
        connectBtn.querySelector("span").textContent = "Opening Login Window...";
        sessionDescText.innerHTML = `<span style="color: var(--primary-color); font-weight:600;">Action Required:</span> A browser window has opened. Please log in manually inside that window. We will automatically detect when you're done.`;
        
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
                    alert("Login session setup timed out. Please try again.");
                }
            }, 2000);
            
        } catch (err) {
            console.error("Failed to start login flow:", err);
            connectBtn.disabled = false;
            connectBtn.querySelector("span").textContent = currentPlatform === 'instagram' ? "Connect Instagram Account" : "Login to Threads (Optional)";
        }
    });

    disconnectBtn.addEventListener("click", async () => {
        if (!confirm(`Are you sure you want to log out and clear your cached ${currentPlatform} session?`)) return;
        
        disconnectBtn.disabled = true;
        disconnectBtn.textContent = "Disconnecting...";
        
        try {
            const res = await fetch(`/api/${currentPlatform}/auth/logout`, { method: "POST" });
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

    openDownloadsBtn.addEventListener("click", async () => {
        try {
            const res = await fetch(`/api/${currentPlatform}/open-folder`, {
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

    // ── Form Submission ─────────────────────────────────────────
    downloadForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        if (currentPlatform === "instagram" && !isConnected) {
            alert("Please connect your Instagram account first.");
            return;
        }

        const url = postUrlInput.value.trim();
        const suffix = filenameSuffixInput.value.trim();
        
        statusCard.style.display = "block";
        statusCard.scrollIntoView({ behavior: "smooth" });
        
        statusTitle.textContent = "Processing Download...";
        statusSpinner.style.display = "block";
        progressBar.style.width = "25%";
        progressBar.style.background = "var(--primary-glow)";
        statusMessage.textContent = "Launching background browser and loading page elements. Please wait...";
        resultPreview.style.display = "none";
        
        submitBtn.disabled = true;
        submitBtn.querySelector("span").textContent = "Downloading...";
        
        try {
            const response = await fetch(`/api/${currentPlatform}/download`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: url, suffix: suffix || null })
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
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
                showDownloadError(result.detail || "Unknown error occurred.");
            }
        } catch (err) {
            showDownloadError("Network error. Make sure the backend server is running.");
        } finally {
            submitBtn.disabled = false;
            submitBtn.querySelector("span").textContent = "Download Post";
        }
    });

    function showDownloadError(message) {
        statusTitle.textContent = "Download Failed";
        statusSpinner.style.display = "none";
        progressBar.style.width = "100%";
        progressBar.style.background = "var(--error-color)";
        statusMessage.innerHTML = `<span style="color: var(--error-color); font-weight: 600;">Error:</span> ${message}`;
        resultPreview.style.display = "none";
    }

    // ── History ─────────────────────────────────────────────────
    async function loadHistory() {
        try {
            const response = await fetch(`/api/${currentPlatform}/history`);
            const result = await response.json();
            
            const cards = historyGrid.querySelectorAll(".history-card");
            cards.forEach(card => card.remove());
            
            if (response.ok && result.history.length > 0) {
                noHistoryState.style.display = "none";
                historyCount.textContent = `${result.history.length} items`;
                
                result.history.forEach(post => {
                    const card = createHistoryCard(post);
                    historyGrid.appendChild(card);
                });
                
                initCarousels();
            } else {
                noHistoryState.style.display = "flex";
                historyCount.textContent = "0 items";
            }
        } catch (err) {
            console.error("Failed to load history list", err);
        }
    }

    function createHistoryCard(post) {
        const card = document.createElement("article");
        card.className = "history-card";
        
        let mediaHtml = "";
        const filesCount = post.media_files.length;
        
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
                </button>
            `;
        }
        
        if (post.is_video && filesCount === 1) {
            mediaHtml += `
                <div class="video-badge">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                        <polygon points="5 3 19 12 5 21 5 3"></polygon>
                    </svg>
                </div>
            `;
        }

        let slidesHtml = "";
        post.media_files.forEach((filename, idx) => {
            const isVideo = filename.toLowerCase().endsWith(".mp4");
            // The post identifier is either shortcode (IG) or post_id (Threads)
            const identifier = currentPlatform === 'instagram' ? post.shortcode : post.post_id;
            const mediaUrl = `/downloads/${currentPlatform}/${identifier}/${filename}`;
            const activeClass = idx === 0 ? "active" : "";
            
            if (isVideo) {
                slidesHtml += `
                    <div class="slide ${activeClass}" data-index="${idx}">
                        <video src="${mediaUrl}" controls loop muted playsinline preload="metadata"></video>
                    </div>
                `;
            } else {
                slidesHtml += `
                    <div class="slide ${activeClass}" data-index="${idx}">
                        <img src="${mediaUrl}" alt="Media item" loading="lazy">
                    </div>
                `;
            }
        });
        
        let dotsHtml = "";
        if (filesCount > 1) {
            dotsHtml += '<div class="carousel-dots">';
            post.media_files.forEach((_, idx) => {
                dotsHtml += `<span class="carousel-dot ${idx === 0 ? "active" : ""}" data-index="${idx}"></span>`;
            });
            dotsHtml += '</div>';
        }
        
        const cleanCaption = post.caption ? escapeHTML(post.caption) : "No caption";
        const cleanDate = formatDate(post.downloaded_at);
        const authorLinkUrl = currentPlatform === 'instagram' ? `https://instagram.com/${post.owner_username}` : `https://www.threads.net/@${post.owner_username}`;
        const platformName = currentPlatform === 'instagram' ? 'Instagram' : 'Threads';

        card.innerHTML = `
            <div class="card-media-container">
                ${mediaHtml}
                ${slidesHtml}
                ${dotsHtml}
            </div>
            <div class="card-details">
                <div class="card-author-row">
                    <a href="${authorLinkUrl}" target="_blank" rel="noopener" class="author-link">@${post.owner_username}</a>
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
                        <span>${platformName}</span>
                    </a>
                    <button type="button" class="card-btn card-btn-folder btn-open-card-folder">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                        </svg>
                        <span>Open Folder</span>
                    </button>
                </div>
            </div>
        `;
        
        const folderBtn = card.querySelector(".btn-open-card-folder");
        folderBtn.addEventListener("click", async () => {
            try {
                const identifierData = currentPlatform === 'instagram' ? { shortcode: post.shortcode } : { post_id: post.post_id };
                await fetch(`/api/${currentPlatform}/open-folder`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(identifierData)
                });
            } catch (err) {
                console.error("Failed to open card folder", err);
            }
        });
        
        return card;
    }

    function initCarousels() {
        const containers = document.querySelectorAll(".card-media-container");
        
        containers.forEach(container => {
            const slides = container.querySelectorAll(".slide");
            if (slides.length <= 1) return;
            
            const btnPrev = container.querySelector(".carousel-btn-prev");
            const btnNext = container.querySelector(".carousel-btn-next");
            const dots = container.querySelectorAll(".carousel-dot");
            
            let currentIndex = 0;
            
            function showSlide(index) {
                const currentVideo = slides[currentIndex].querySelector("video");
                if (currentVideo) currentVideo.pause();
                
                slides[currentIndex].classList.remove("active");
                if (dots.length > 0) dots[currentIndex].classList.remove("active");
                
                currentIndex = (index + slides.length) % slides.length;
                slides[currentIndex].classList.add("active");
                if (dots.length > 0) dots[currentIndex].classList.add("active");
                
                const nextVideo = slides[currentIndex].querySelector("video");
                if (nextVideo) nextVideo.play().catch(() => {});
            }
            
            btnPrev.addEventListener("click", (e) => { e.stopPropagation(); showSlide(currentIndex - 1); });
            btnNext.addEventListener("click", (e) => { e.stopPropagation(); showSlide(currentIndex + 1); });
            dots.forEach((dot, idx) => {
                dot.addEventListener("click", (e) => { e.stopPropagation(); showSlide(idx); });
            });
        });
    }

    function escapeHTML(str) {
        return str.replace(/[&<>'"]/g, tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag));
    }

    function formatDate(dateStr) {
        try {
            const date = new Date(dateStr);
            return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
        } catch (e) {
            return dateStr;
        }
    }
});
