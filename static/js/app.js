document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const downloadForm = document.getElementById("download-form");
    const postUrlInput = document.getElementById("post-url");
    const filenameSuffixInput = document.getElementById("filename-suffix");
    const submitBtn = document.getElementById("submit-btn");
    const openDownloadsBtn = document.getElementById("open-downloads-btn");
    
    // Auth Session Manager Elements
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

    // State Variables
    let isConnected = false;
    let authPollingInterval = null;

    // Initialize Page
    checkAuthStatus();
    loadHistory();

    // Check Instagram Session Status
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

    // Update UI based on connection state
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
            submitBtn.querySelector("span").textContent = "Download Post";
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

    // Trigger Headed Interactive Login
    connectBtn.addEventListener("click", async () => {
        connectBtn.disabled = true;
        connectBtn.querySelector("span").textContent = "Opening Login Window...";
        sessionDescText.innerHTML = `<span style="color: var(--primary-color); font-weight:600;">Action Required:</span> A browser window has opened. Please log in manually inside that window. We will automatically detect when you're done.`;
        
        try {
            // Trigger login flow endpoint in background thread
            fetch("/api/auth/login", { method: "POST" })
                .then(res => res.json())
                .then(data => {
                    logger.info("Login flow process returned:", data);
                })
                .catch(err => console.error("Login call failed", err));
            
            // Start polling for status changes
            if (authPollingInterval) clearInterval(authPollingInterval);
            
            let pollCounter = 0;
            authPollingInterval = setInterval(async () => {
                pollCounter++;
                const authenticated = await checkAuthStatus();
                
                if (authenticated) {
                    clearInterval(authPollingInterval);
                    connectBtn.querySelector("span").textContent = "Connect Instagram Account";
                }
                
                // Timeout polling after 3 minutes (90 polls of 2s)
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

    // Disconnect/Logout Session
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

    // Open Main Downloads Folder
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

    // Form Submission for Download
    downloadForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        if (!isConnected) {
            alert("Please connect your Instagram account first.");
            return;
        }

        const url = postUrlInput.value.trim();
        const suffix = filenameSuffixInput.value.trim();
        
        // Show status card
        statusCard.style.display = "block";
        statusCard.scrollIntoView({ behavior: "smooth" });
        
        // Reset status card
        statusTitle.textContent = "Processing Download...";
        statusSpinner.style.display = "block";
        progressBar.style.width = "25%";
        progressBar.style.background = "var(--primary-glow)";
        statusMessage.textContent = "Launching background browser and loading page elements. Please wait...";
        resultPreview.style.display = "none";
        
        // Disable controls
        submitBtn.disabled = true;
        submitBtn.querySelector("span").textContent = "Downloading...";
        
        try {
            const response = await fetch("/api/download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    url: url,
                    suffix: suffix || null
                })
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                // Success State
                statusTitle.textContent = "Download Complete!";
                statusSpinner.style.display = "none";
                progressBar.style.width = "100%";
                statusMessage.textContent = "Post downloaded successfully to your local machine.";
                
                // Show result details
                resultUsername.textContent = `@${result.data.owner_username}`;
                resultCaption.textContent = result.data.caption || "No caption";
                resultMediaCount.textContent = `Downloaded ${result.data.media_files.length} media file(s).`;
                resultPreview.style.display = "flex";
                
                // Reset form URL and suffix inputs
                postUrlInput.value = "";
                filenameSuffixInput.value = "";
                
                // Reload history
                loadHistory();
            } else {
                // Error State from server
                const errDetail = result.detail || "Unknown error occurred.";
                showDownloadError(errDetail);
            }
        } catch (err) {
            // General Network error
            showDownloadError("Network error. Make sure the backend server is running.");
        } finally {
            // Enable controls
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

    // Load downloaded posts history
    async function loadHistory() {
        try {
            const response = await fetch("/api/history");
            const result = await response.json();
            
            if (response.ok && result.history.length > 0) {
                noHistoryState.style.display = "none";
                historyCount.textContent = `${result.history.length} items`;
                
                // Clear old cards
                const cards = historyGrid.querySelectorAll(".history-card");
                cards.forEach(card => card.remove());
                
                result.history.forEach(post => {
                    const card = createHistoryCard(post);
                    historyGrid.appendChild(card);
                });
                
                // Initialize carousels after injecting cards
                initCarousels();
            } else {
                // Remove existing cards
                const cards = historyGrid.querySelectorAll(".history-card");
                cards.forEach(card => card.remove());
                
                noHistoryState.style.display = "flex";
                historyCount.textContent = "0 items";
            }
        } catch (err) {
            console.error("Failed to load history list", err);
        }
    }

    // Create a history card node
    function createHistoryCard(post) {
        const card = document.createElement("article");
        card.className = "history-card";
        card.dataset.shortcode = post.shortcode;
        
        // Media markup
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

        // Render slides
        let slidesHtml = "";
        post.media_files.forEach((filename, idx) => {
            const isVideo = filename.toLowerCase().endsWith(".mp4");
            const mediaUrl = `/downloads/${post.shortcode}/${filename}`;
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
                        <img src="${mediaUrl}" alt="Instagram post item" loading="lazy">
                    </div>
                `;
            }
        });
        
        // Render dots
        let dotsHtml = "";
        if (filesCount > 1) {
            dotsHtml += '<div class="carousel-dots">';
            post.media_files.forEach((_, idx) => {
                dotsHtml += `<span class="carousel-dot ${idx === 0 ? "active" : ""}" data-index="${idx}"></span>`;
            });
            dotsHtml += '</div>';
        }
        
        // Assemble Card Content
        const cleanCaption = post.caption ? escapeHTML(post.caption) : "No caption";
        const cleanDate = formatDate(post.downloaded_at);

        card.innerHTML = `
            <div class="card-media-container">
                ${mediaHtml}
                ${slidesHtml}
                ${dotsHtml}
            </div>
            <div class="card-details">
                <div class="card-author-row">
                    <a href="https://instagram.com/${post.owner_username}" target="_blank" rel="noopener" class="author-link">@${post.owner_username}</a>
                    <span class="download-date">${cleanDate}</span>
                </div>
                <p class="card-caption" title="${cleanCaption}">${cleanCaption}</p>
                <div class="card-stats" style="display: none;">
                    <!-- Hide stats since we are not scraping likes/comments to reduce load -->
                </div>
                <div class="card-actions">
                    <a href="${post.url}" target="_blank" rel="noopener" class="card-btn card-btn-view">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                            <polyline points="15 3 21 3 21 9"></polyline>
                            <line x1="10" y1="14" x2="21" y2="3"></line>
                        </svg>
                        <span>Instagram</span>
                    </a>
                    <button type="button" class="card-btn card-btn-folder btn-open-card-folder" data-shortcode="${post.shortcode}">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                        </svg>
                        <span>Open Folder</span>
                    </button>
                </div>
            </div>
        `;
        
        // Add single card action listener
        const folderBtn = card.querySelector(".btn-open-card-folder");
        folderBtn.addEventListener("click", async () => {
            try {
                await fetch("/api/open-folder", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ shortcode: post.shortcode })
                });
            } catch (err) {
                console.error("Failed to open card folder", err);
            }
        });
        
        return card;
    }

    // Setup interactive carousels for multi-slide posts
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
                // Pause any playing videos
                const currentVideo = slides[currentIndex].querySelector("video");
                if (currentVideo) {
                    currentVideo.pause();
                }
                
                // Deactivate current
                slides[currentIndex].classList.remove("active");
                if (dots.length > 0) dots[currentIndex].classList.remove("active");
                
                // Activate new index
                currentIndex = (index + slides.length) % slides.length;
                slides[currentIndex].classList.add("active");
                if (dots.length > 0) dots[currentIndex].classList.add("active");
                
                // Play video if active
                const nextVideo = slides[currentIndex].querySelector("video");
                if (nextVideo) {
                    nextVideo.play().catch(() => {});
                }
            }
            
            btnPrev.addEventListener("click", (e) => {
                e.stopPropagation();
                showSlide(currentIndex - 1);
            });
            
            btnNext.addEventListener("click", (e) => {
                e.stopPropagation();
                showSlide(currentIndex + 1);
            });
            
            dots.forEach((dot, idx) => {
                dot.addEventListener("click", (e) => {
                    e.stopPropagation();
                    showSlide(idx);
                });
            });
        });
    }

    // Helper functions
    function escapeHTML(str) {
        return str.replace(/[&<>'"]/g, 
            tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
        );
    }

    function formatDate(dateStr) {
        try {
            const date = new Date(dateStr);
            return date.toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric"
            });
        } catch (e) {
            return dateStr;
        }
    }
});
