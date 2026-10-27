document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const syncBtn = document.getElementById("sync-btn");
    const statusCard = document.getElementById("status-card");
    const statusTitle = document.getElementById("status-title");
    const statusSpinner = document.getElementById("status-spinner");
    const progressBar = document.getElementById("progress-bar");
    const statusMessage = document.getElementById("status-message");
    const postsGallery = document.getElementById("posts-gallery");
    const noPosts = document.getElementById("no-posts");
    const noPostsText = document.getElementById("no-posts-text");
    const postsCount = document.getElementById("posts-count");

    let allPosts = [];

    // ── Auto Load on Page Init ────────────────────────────────────
    async function loadInitialPosts() {
        try {
            const res = await fetch("/api/spreadsheet/posts");
            const data = await res.json();
            if (res.ok && data.success && data.posts && data.posts.length > 0) {
                allPosts = data.posts;
                renderGallery(allPosts);
            }
        } catch (e) {
            console.log("Initial posts load skipped/failed", e);
        }
    }
    loadInitialPosts();

    // ── Sync ──────────────────────────────────────────────────────
    syncBtn.addEventListener("click", async () => {
        statusCard.style.display = "flex";
        statusTitle.textContent = "Syncing from Google Sheet...";
        statusSpinner.style.display = "block";
        progressBar.style.width = "25%";
        progressBar.style.background = "var(--primary-glow)";
        statusMessage.textContent = "Reading spreadsheet data and processing pending posts...";
        syncBtn.disabled = true;

        try {
            const res = await fetch("/api/spreadsheet/sync", { method: "POST" });
            const data = await res.json();

            if (res.ok && data.success) {
                statusTitle.textContent = "Sync Complete";
                statusSpinner.style.display = "none";
                progressBar.style.width = "100%";
                progressBar.style.background = "var(--success-color)";
                const counts = [
                    data.pending_count > 0 ? `${data.pending_count} pending` : null,
                    data.s3_count > 0 ? `${data.s3_count} on S3` : null,
                    data.renamed_count > 0 ? `${data.renamed_count} renamed` : null,
                    data.downloaded_count > 0 ? `${data.downloaded_count} downloaded` : null,
                ].filter(Boolean).join(", ");
                statusMessage.textContent = `Loaded ${data.posts.length} posts. ${counts || "No posts yet."}`;

                allPosts = data.posts;
                renderGallery(allPosts);

                setTimeout(() => { statusCard.style.display = "none"; }, 3500);
            } else {
                showError("Sync failed: " + (data.detail || "Unknown error"));
            }
        } catch (err) {
            showError("Network error while syncing.");
        } finally {
            syncBtn.disabled = false;
        }
    });

    // ── Render Gallery ───────────────────────────────────────────
    function renderGallery(posts) {
        // Clear existing cards but keep the no-posts placeholder
        const existingCards = postsGallery.querySelectorAll(".spreadsheet-post-card");
        existingCards.forEach(el => el.remove());

        if (posts.length === 0) {
            noPosts.style.display = "flex";
            noPostsText.textContent = "No posts found.";
            postsCount.textContent = "0 items";
            return;
        }

        noPosts.style.display = "none";
        postsCount.textContent = `${posts.length} items`;

        posts.forEach((post) => {
            const card = document.createElement("article");
            card.className = "spreadsheet-post-card";

            const meta = post.metadata || {};
            const identifier = meta.shortcode || meta.post_id || "";
            const platform = post.platform || "instagram";

            // Determine username with robust fallbacks
            let username = post.username || meta.owner_username || "";
            if (!username || username === "instagram_user") {
                username = meta.owner_username || post.username || "instagram_user";
            }

            const profileUrl = platform === "instagram"
                ? `https://instagram.com/${username}`
                : `https://www.threads.net/@${username}`;
            const platformLabel = platform === "instagram" ? "Instagram" : "Threads";

            // Status class
            let statusClass = "status-pending";
            if (post.status === "S3") statusClass = "status-s3";
            else if (post.status === "RENAMED") statusClass = "status-renamed";
            else if (post.status === "DOWNLOADED") statusClass = "status-downloaded";

            // Thumbnail
            let thumbnailHtml;
            if (post.thumbnail_url) {
                thumbnailHtml = `<img src="${escapeHTML(post.thumbnail_url)}" alt="Post thumbnail" loading="lazy">`;
            } else if (meta.media_files && meta.media_files.length > 0) {
                const firstFile = meta.media_files[0];
                const fallbackThumb = `/downloads/${platform}/${identifier}/${firstFile}`;
                thumbnailHtml = `<img src="${escapeHTML(fallbackThumb)}" alt="Post thumbnail" loading="lazy">`;
            } else {
                thumbnailHtml = `
                    <div class="thumbnail-placeholder">
                        <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5">
                            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                            <circle cx="8.5" cy="8.5" r="1.5"></circle>
                            <polyline points="21 15 16 10 5 21"></polyline>
                        </svg>
                    </div>
                `;
            }

            // Profile bio
            const bioText = post.profile_bio || meta.profile_bio || "";
            const bioHtml = bioText
                ? `<p class="card-profile-bio" title="${escapeHTML(bioText)}">${escapeHTML(bioText)}</p>`
                : "";

            // Caption
            const captionText = post.caption || meta.caption || "";
            const captionHtml = captionText
                ? `<p class="card-caption" title="${escapeHTML(captionText)}">${escapeHTML(captionText)}</p>`
                : `<p class="card-caption card-caption-empty">No caption</p>`;

            // Usernames
            let usernamesHtml = `<a href="${profileUrl}" target="_blank" rel="noopener" class="author-link">@${escapeHTML(username)}</a>`;
            const usernamesList = post.profile_usernames || meta.profile_usernames || [];
            if (usernamesList.length > 1) {
                const others = usernamesList.filter(u => u !== username && u !== "instagram_user");
                others.forEach(u => {
                    const otherUrl = platform === "instagram"
                        ? `https://instagram.com/${u}`
                        : `https://www.threads.net/@${u}`;
                    usernamesHtml += `, <a href="${otherUrl}" target="_blank" rel="noopener" class="author-link">@${escapeHTML(u)}</a>`;
                });
            }

            // Action buttons
            let actionsHtml = "";
            const currentSuffix = post.suffix || meta.suffix || "";
            card.dataset.suffix = currentSuffix;

            // Rename controls for S3 or RENAMED posts
            if (post.status === "S3" || post.status === "RENAMED") {
                actionsHtml += `
                    <div class="card-action-row">
                        <input type="text" class="rename-suffix-input" placeholder="Suffix (e.g. _vacation)" value="${escapeHTML(currentSuffix)}" data-url="${escapeHTML(post.link)}">
                        <button type="button" class="card-btn card-btn-rename btn-rename-post" data-url="${escapeHTML(post.link)}">
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                            </svg>
                            <span>Rename</span>
                        </button>
                    </div>
                `;
            }

            // Download button for S3 or RENAMED posts
            if (post.status === "S3" || post.status === "RENAMED") {
                actionsHtml += `
                    <button type="button" class="card-btn card-btn-download btn-download-local" data-url="${escapeHTML(post.link)}">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                            <polyline points="7 10 12 15 17 10"></polyline>
                            <line x1="12" y1="15" x2="12" y2="3"></line>
                        </svg>
                        <span>Download</span>
                    </button>
                `;
            }

            // Suffix copy + Open folder button for DOWNLOADED posts
            if (post.status === "DOWNLOADED") {
                actionsHtml += buildDownloadedActionsHtml(identifier, currentSuffix);
            }

            const folderName = post.identifier || identifier || "";
            const folderHtml = folderName ? `
                <span class="card-folder-badge" title="Folder name: ${escapeHTML(folderName)}">
                    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                    </svg>
                    ${escapeHTML(folderName)}
                </span>
            ` : "";

            card.innerHTML = `
                <div class="card-thumbnail">
                    ${thumbnailHtml}
                </div>
                <div class="card-details">
                    <div class="card-header-row">
                        <div class="card-usernames">${usernamesHtml}</div>
                        <div class="card-header-meta">
                            ${folderHtml}
                            <span class="status-badge ${statusClass}">${escapeHTML(post.status)}</span>
                        </div>
                    </div>
                    ${bioHtml}
                    <a href="${escapeHTML(post.link)}" target="_blank" rel="noopener" class="card-post-link">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                            <polyline points="15 3 21 3 21 9"></polyline>
                            <line x1="10" y1="14" x2="21" y2="3"></line>
                        </svg>
                        View on ${platformLabel}
                    </a>
                    ${captionHtml}
                    <div class="card-actions">
                        ${actionsHtml}
                    </div>
                </div>
            `;

            postsGallery.appendChild(card);
        });

        // Attach event listeners
        attachCardEventListeners();
    }

    function buildDownloadedActionsHtml(identifier, suffix) {
        let html = "";
        if (suffix) {
            html += `
                <div class="card-action-row">
                    <input type="text" class="rename-suffix-input suffix-readonly" value="${escapeHTML(suffix)}" readonly title="Suffix: ${escapeHTML(suffix)}">
                    <button type="button" class="card-btn card-btn-copy btn-copy-suffix" data-suffix="${escapeHTML(suffix)}">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
                        <span>Copy</span>
                    </button>
                </div>
            `;
        }
        html += `
            <button type="button" class="card-btn card-btn-folder btn-open-card-folder" data-identifier="${escapeHTML(identifier)}">
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                </svg>
                <span>Open Folder</span>
            </button>
        `;
        return html;
    }

    function bindOpenFolderButton(btn) {
        btn.addEventListener("click", async () => {
            try {
                await fetch("/api/spreadsheet/open-folder", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ identifier: btn.dataset.identifier }),
                });
            } catch (err) {
                console.error("Failed to open folder", err);
            }
        });
    }

    function bindCopySuffixButton(btn) {
        btn.addEventListener("click", async () => {
            const suffix = btn.dataset.suffix || "";
            if (!suffix) return;

            try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(suffix);
                } else {
                    const tempInput = document.createElement("textarea");
                    tempInput.value = suffix;
                    document.body.appendChild(tempInput);
                    tempInput.select();
                    document.execCommand("copy");
                    document.body.removeChild(tempInput);
                }

                const btnText = btn.querySelector("span");
                const originalText = btnText ? btnText.textContent : "Copy";
                if (btnText) btnText.textContent = "Copied ✓";
                btn.style.background = "rgba(34, 197, 94, 0.25)";
                btn.style.color = "rgb(74, 222, 128)";
                setTimeout(() => {
                    if (btnText) btnText.textContent = originalText;
                    btn.style.background = "";
                    btn.style.color = "";
                }, 2000);
            } catch (err) {
                console.error("Failed to copy suffix", err);
            }
        });
    }

    // ── Card Event Listeners ──────────────────────────────────────
    function attachCardEventListeners() {
        // Rename
        document.querySelectorAll(".btn-rename-post").forEach(btn => {
            btn.addEventListener("click", async () => {
                const url = btn.dataset.url;
                const actionRow = btn.closest(".card-action-row");
                const suffixInput = actionRow ? actionRow.querySelector(".rename-suffix-input") : null;
                const suffix = suffixInput ? suffixInput.value.trim() : "";

                if (!suffix) {
                    alert("Please enter a suffix.");
                    return;
                }

                btn.disabled = true;
                const btnText = btn.querySelector("span");
                const originalText = btnText ? btnText.textContent : "Rename";
                if (btnText) btnText.textContent = "Renaming...";

                try {
                    const res = await fetch("/api/spreadsheet/rename", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ url, suffix }),
                    });
                    const data = await res.json();
                    if (res.ok && data.success) {
                        const card = btn.closest(".spreadsheet-post-card");
                        if (card) {
                            card.dataset.suffix = data.suffix || suffix;
                            // Update status badge
                            const badge = card.querySelector(".status-badge");
                            if (badge) {
                                badge.className = "status-badge status-renamed";
                                badge.textContent = "RENAMED";
                            }
                            // Update thumbnail image
                            if (data.thumbnail_url) {
                                const img = card.querySelector(".card-thumbnail img");
                                if (img) {
                                    img.src = data.thumbnail_url;
                                }
                            }
                        }
                        if (btnText) btnText.textContent = "Renamed ✓";
                        btn.style.background = "rgba(34, 197, 94, 0.25)";
                        btn.style.color = "rgb(74, 222, 128)";
                        setTimeout(() => {
                            btn.disabled = false;
                            if (btnText) btnText.textContent = originalText;
                            btn.style.background = "";
                            btn.style.color = "";
                        }, 2000);
                    } else {
                        alert("Rename failed: " + (data.detail || "Unknown error"));
                        btn.disabled = false;
                        if (btnText) btnText.textContent = originalText;
                    }
                } catch (err) {
                    alert("Network error during rename.");
                    btn.disabled = false;
                    if (btnText) btnText.textContent = originalText;
                }
            });
        });

        // Download (S3 -> Local)
        document.querySelectorAll(".btn-download-local").forEach(btn => {
            btn.addEventListener("click", async () => {
                const url = btn.dataset.url;

                btn.disabled = true;
                const btnText = btn.querySelector("span");
                const originalText = btnText ? btnText.textContent : "Download";
                if (btnText) btnText.textContent = "Downloading...";

                try {
                    const res = await fetch("/api/spreadsheet/download", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ url }),
                    });
                    const data = await res.json();
                    if (res.ok && data.success) {
                        const card = btn.closest(".spreadsheet-post-card");
                        if (card) {
                            // Update status badge
                            const badge = card.querySelector(".status-badge");
                            if (badge) {
                                badge.className = "status-badge status-downloaded";
                                badge.textContent = "DOWNLOADED";
                            }
                            // Preserve suffix and replace card actions with Copy + Open Folder buttons
                            const actionsContainer = card.querySelector(".card-actions");
                            const folderBadge = card.querySelector(".card-folder-badge");
                            const identifier = folderBadge ? folderBadge.textContent.trim() : "";
                            const suffixInput = card.querySelector(".rename-suffix-input");
                            const currentSuffix = (suffixInput ? suffixInput.value.trim() : "") || data.suffix || card.dataset.suffix || "";
                            card.dataset.suffix = currentSuffix;
                            if (actionsContainer) {
                                actionsContainer.innerHTML = buildDownloadedActionsHtml(identifier, currentSuffix);
                                const openBtn = actionsContainer.querySelector(".btn-open-card-folder");
                                if (openBtn) bindOpenFolderButton(openBtn);
                                const copyBtn = actionsContainer.querySelector(".btn-copy-suffix");
                                if (copyBtn) bindCopySuffixButton(copyBtn);
                            }
                        }
                    } else {
                        alert("Download failed: " + (data.detail || "Unknown error"));
                        btn.disabled = false;
                        if (btnText) btnText.textContent = originalText;
                    }
                } catch (err) {
                    alert("Network error during download.");
                    btn.disabled = false;
                    if (btnText) btnText.textContent = originalText;
                }
            });
        });

        // Open Folder
        document.querySelectorAll(".btn-open-card-folder").forEach(btn => {
            bindOpenFolderButton(btn);
        });

        // Copy Suffix
        document.querySelectorAll(".btn-copy-suffix").forEach(btn => {
            bindCopySuffixButton(btn);
        });
    }

    // ── Helpers ──────────────────────────────────────────────────
    function showStatus(title, message, bgColor) {
        statusCard.style.display = "flex";
        statusTitle.textContent = title;
        statusSpinner.style.display = "none";
        progressBar.style.width = "100%";
        progressBar.style.background = bgColor || "var(--success-color)";
        statusMessage.textContent = message;
        setTimeout(() => { statusCard.style.display = "none"; }, 3000);
    }

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
});
