document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const syncBtn = document.getElementById("sync-btn");
    const downloadPendingBtn = document.getElementById("download-pending-btn");
    const statusCard = document.getElementById("status-card");
    const statusTitle = document.getElementById("status-title");
    const statusSpinner = document.getElementById("status-spinner");
    const progressBar = document.getElementById("progress-bar");
    const statusMessage = document.getElementById("status-message");
    const postsContainer = document.getElementById("posts-table-container");
    const noPosts = document.getElementById("no-posts");
    const noPostsText = document.getElementById("no-posts-text");
    const postsCount = document.getElementById("posts-count");
    const gallerySection = document.getElementById("gallery-section");
    const galleryGrid = document.getElementById("gallery-grid");
    const galleryCount = document.getElementById("gallery-count");

    let allPosts = [];

    // ── Sync ──────────────────────────────────────────────────────
    syncBtn.addEventListener("click", async () => {
        statusCard.style.display = "flex";
        statusCard.scrollIntoView({ behavior: "smooth" });
        statusTitle.textContent = "Syncing from Google Sheets...";
        statusSpinner.style.display = "block";
        progressBar.style.width = "25%";
        progressBar.style.background = "var(--primary-glow)";
        statusMessage.textContent = "Reading spreadsheet data...";
        syncBtn.disabled = true;

        try {
            const res = await fetch("/api/spreadsheet/sync", { method: "POST" });
            const data = await res.json();

            if (res.ok && data.success) {
                statusTitle.textContent = "Sync Complete";
                statusSpinner.style.display = "none";
                progressBar.style.width = "100%";
                statusMessage.textContent = `Loaded ${data.posts.length} posts. ${data.pending_count} pending, ${data.downloaded_count} downloaded.`;

                allPosts = data.posts;
                renderPostsTable(allPosts);
                renderGallery(allPosts);
            } else {
                showError("Sync failed: " + (data.detail || "Unknown error"));
            }
        } catch (err) {
            showError("Network error while syncing.");
        } finally {
            syncBtn.disabled = false;
        }
    });

    // ── Download Pending ──────────────────────────────────────────
    downloadPendingBtn.addEventListener("click", async () => {
        statusCard.style.display = "flex";
        statusCard.scrollIntoView({ behavior: "smooth" });
        statusTitle.textContent = "Downloading Pending Posts to S3...";
        statusSpinner.style.display = "block";
        progressBar.style.width = "5%";
        progressBar.style.background = "var(--primary-glow)";
        statusMessage.textContent = "Starting batch download...";
        downloadPendingBtn.disabled = true;

        try {
            const res = await fetch("/api/spreadsheet/download-pending", { method: "POST" });
            const data = await res.json();

            if (res.ok) {
                progressBar.style.width = "100%";
                statusSpinner.style.display = "none";
                statusTitle.textContent = "Batch Download Complete";
                statusMessage.textContent = `Succeeded: ${data.succeeded}, Failed: ${data.failed} out of ${data.total_pending} pending posts.`;

                if (data.failed > 0) {
                    progressBar.style.background = "linear-gradient(90deg, var(--success-color) 50%, var(--error-color) 100%)";
                } else {
                    progressBar.style.background = "var(--success-color)";
                }

                setTimeout(() => {
                    statusCard.style.display = "none";
                }, 3000);

                syncBtn.click();
            } else {
                showError("Download failed: " + (data.detail || "Unknown error"));
            }
        } catch (err) {
            showError("Network error while downloading pending posts.");
        } finally {
            downloadPendingBtn.disabled = false;
        }
    });

    // ── Render Posts Table ────────────────────────────────────────
    function renderPostsTable(posts) {
        const existing = postsContainer.querySelectorAll(".posts-table");
        existing.forEach(el => el.remove());

        if (posts.length === 0) {
            noPosts.style.display = "flex";
            noPostsText.textContent = "No posts found.";
            postsCount.textContent = "0 items";
            return;
        }

        noPosts.style.display = "none";
        postsCount.textContent = `${posts.length} items`;

        const table = document.createElement("div");
        table.className = "posts-table";

        const header = document.createElement("div");
        header.className = "posts-table-header";
        header.innerHTML = `
            <div class="post-cell post-cell-datetime">Datetime</div>
            <div class="post-cell post-cell-link">Link</div>
            <div class="post-cell post-cell-rectified">Rectified Link</div>
            <div class="post-cell post-cell-username">Username</div>
            <div class="post-cell post-cell-platform">Platform</div>
            <div class="post-cell post-cell-status">Status</div>
            <div class="post-cell post-cell-actions">Actions</div>
        `;
        table.appendChild(header);

        posts.forEach((post, index) => {
            const row = document.createElement("div");
            row.className = "posts-table-row";

            const statusClass = post.status === "DOWNLOADED" ? "status-downloaded" : "status-pending";
            const rectified = post.rectified_link || post.link;
            const hasMetadata = post.metadata && post.metadata.media_files && post.metadata.media_files.length > 0;

            row.innerHTML = `
                <div class="post-cell post-cell-datetime">${escapeHTML(post.datetime)}</div>
                <div class="post-cell post-cell-link">
                    <a href="${escapeHTML(post.link)}" target="_blank" rel="noopener" class="post-link">${escapeHTML(post.link)}</a>
                </div>
                <div class="post-cell post-cell-rectified">
                    ${post.rectified_link ? `<a href="${escapeHTML(post.rectified_link)}" target="_blank" rel="noopener" class="post-link">${escapeHTML(post.rectified_link)}</a>` : "-"}
                </div>
                <div class="post-cell post-cell-username">@${escapeHTML(post.username)}</div>
                <div class="post-cell post-cell-platform">${escapeHTML(post.platform)}</div>
                <div class="post-cell post-cell-status">
                    <span class="status-badge ${statusClass}">${escapeHTML(post.status)}</span>
                </div>
                <div class="post-cell post-cell-actions">
                    ${post.status === "PENDING" ? `<span class="no-action">Pending S3</span>` : ""}
                    ${post.status === "DOWNLOADED" ? `
                        <input type="text" class="row-suffix-input spreadsheet-suffix" data-url="${escapeHTML(post.link)}" placeholder="Suffix (Optional)">
                        <button type="button" class="btn btn-download-post" data-url="${escapeHTML(post.link)}" data-rectified="${escapeHTML(rectified)}">
                            Download
                        </button>
                    ` : ""}
                </div>
            `;

            table.appendChild(row);
        });

        postsContainer.appendChild(table);

        document.querySelectorAll(".btn-download-post").forEach(btn => {
            btn.addEventListener("click", async () => {
                const url = btn.dataset.url;
                const rectified = btn.dataset.rectified;
                const suffixInput = btn.parentElement.querySelector(".spreadsheet-suffix");
                const suffix = suffixInput ? suffixInput.value.trim() : "";

                btn.disabled = true;
                btn.querySelector("span") && btn.querySelector("span").textContent && btn.querySelector("span").textContent !== "Download" && (btn.textContent = "Downloading...");
                btn.textContent = "Downloading...";

                try {
                    const res = await fetch("/api/spreadsheet/download-post", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ url, suffix: suffix || null, rectified_link: rectified || url }),
                    });
                    const data = await res.json();
                    if (res.ok && data.success) {
                        btn.textContent = "Done!";
                        btn.classList.add("btn-success");
                        statusMessage.textContent = `Downloaded post from @${data.data.owner_username}`;
                        statusCard.style.display = "flex";
                        statusCard.scrollIntoView({ behavior: "smooth" });
                        statusTitle.textContent = "Download Complete";
                        statusSpinner.style.display = "none";
                        progressBar.style.width = "100%";
                        progressBar.style.background = "var(--success-color)";
                        setTimeout(() => { statusCard.style.display = "none"; }, 2000);
                        syncBtn.click();
                    } else {
                        btn.textContent = "Retry";
                        btn.disabled = false;
                        alert("Download failed: " + (data.detail || "Unknown error"));
                    }
                } catch (err) {
                    btn.textContent = "Retry";
                    btn.disabled = false;
                    alert("Network error during download.");
                }
            });
        });
    }

    // ── Render Gallery ───────────────────────────────────────────
    function renderGallery(posts) {
        galleryGrid.innerHTML = "";
        const downloadedPosts = posts.filter(p => p.status === "DOWNLOADED" && p.metadata);

        if (downloadedPosts.length === 0) {
            gallerySection.style.display = "none";
            return;
        }

        gallerySection.style.display = "flex";
        gallerySection.style.flexDirection = "column";
        gallerySection.style.gap = "20px";
        galleryCount.textContent = `${downloadedPosts.length} items`;

        downloadedPosts.forEach(post => {
            const meta = post.metadata;
            const card = document.createElement("article");
            card.className = "history-card";

            const filesCount = meta.media_files.length;
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
                    </button>
                `;
            }

            if (meta.is_video && filesCount === 1) {
                mediaHtml += `
                    <div class="video-badge">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                            <polygon points="5 3 19 12 5 21 5 3"></polygon>
                        </svg>
                    </div>
                `;
            }

            let slidesHtml = "";
            meta.media_files.forEach((filename, idx) => {
                const isVideo = filename.toLowerCase().endsWith(".mp4");
                const identifier = meta.shortcode || meta.post_id;
                const platform = post.platform || "instagram";
                const mediaUrl = `/downloads/${platform}/${identifier}/${filename}`;
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
                meta.media_files.forEach((_, idx) => {
                    dotsHtml += `<span class="carousel-dot ${idx === 0 ? "active" : ""}" data-index="${idx}"></span>`;
                });
                dotsHtml += '</div>';
            }

            const cleanCaption = meta.caption ? escapeHTML(meta.caption) : "No caption";
            const cleanDate = formatDate(meta.downloaded_at);
            const authorLinkUrl = post.platform === "instagram" ? `https://instagram.com/${meta.owner_username}` : `https://www.threads.net/@${meta.owner_username}`;
            const platformName = post.platform === "instagram" ? "Instagram" : "Threads";

            card.innerHTML = `
                <div class="card-media-container">
                    ${mediaHtml}
                    ${slidesHtml}
                    ${dotsHtml}
                </div>
                <div class="card-details">
                    <div class="card-author-row">
                        <a href="${authorLinkUrl}" target="_blank" rel="noopener" class="author-link">@${meta.owner_username}</a>
                        <span class="download-date">${cleanDate}</span>
                    </div>
                    <p class="card-caption" title="${cleanCaption}">${cleanCaption}</p>
                    <div class="card-actions">
                        <a href="${post.link}" target="_blank" rel="noopener" class="card-btn card-btn-view">
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                                <polyline points="15 3 21 3 21 9"></polyline>
                                <line x1="10" y1="14" x2="21" y2="3"></line>
                            </svg>
                            <span>${platformName}</span>
                        </a>
                        <button type="button" class="card-btn card-btn-folder btn-open-card-folder" data-identifier="${meta.shortcode || meta.post_id}">
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
                    await fetch(`/api/spreadsheet/open-folder`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ identifier: folderBtn.dataset.identifier })
                    });
                } catch (err) {
                    console.error("Failed to open folder", err);
                }
            });

            galleryGrid.appendChild(card);
        });

        initCarousels();
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

    // ── Helpers ──────────────────────────────────────────────────
    function showError(message) {
        statusTitle.textContent = "Error";
        statusSpinner.style.display = "none";
        progressBar.style.width = "100%";
        progressBar.style.background = "var(--error-color)";
        statusMessage.innerHTML = `<span style="color: var(--error-color); font-weight: 600;">Error:</span> ${message}`;
    }

    function escapeHTML(str) {
        if (!str) return "";
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
