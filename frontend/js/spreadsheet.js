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
        statusCard.scrollIntoView({ behavior: "smooth" });
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

            // Rename controls for S3 or RENAMED posts
            if (post.status === "S3" || post.status === "RENAMED") {
                actionsHtml += `
                    <div class="card-action-row">
                        <input type="text" class="rename-suffix-input" placeholder="Suffix (e.g. _vacation)" data-url="${escapeHTML(post.link)}">
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
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                            <polyline points="7 10 12 15 17 10"></polyline>
                            <line x1="12" y1="15" x2="12" y2="3"></line>
                        </svg>
                        <span>Download</span>
                    </button>
                `;
            }

            // Open folder button for DOWNLOADED posts
            if (post.status === "DOWNLOADED") {
                actionsHtml += `
                    <button type="button" class="card-btn card-btn-folder btn-open-card-folder" data-identifier="${escapeHTML(identifier)}">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                        </svg>
                        <span>Open Folder</span>
                    </button>
                `;
            }

            card.innerHTML = `
                <div class="card-thumbnail">
                    ${thumbnailHtml}
                </div>
                <div class="card-details">
                    <div class="card-header-row">
                        <div class="card-usernames">${usernamesHtml}</div>
                        <span class="status-badge ${statusClass}">${escapeHTML(post.status)}</span>
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

    // ── Card Event Listeners ──────────────────────────────────────
    function attachCardEventListeners() {
        // Rename
        document.querySelectorAll(".btn-rename-post").forEach(btn => {
            btn.addEventListener("click", async () => {
                const url = btn.dataset.url;
                const suffixInput = btn.closest(".card-action-row").querySelector(".rename-suffix-input");
                const suffix = suffixInput ? suffixInput.value.trim() : "";

                if (!suffix) {
                    alert("Please enter a suffix.");
                    return;
                }

                btn.disabled = true;
                btn.querySelector("span").textContent = "Renaming...";

                try {
                    const res = await fetch("/api/spreadsheet/rename", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ url, suffix }),
                    });
                    const data = await res.json();
                    if (res.ok && data.success) {
                        showStatus("Rename Complete", data.message, "var(--success-color)");
                        syncBtn.click();
                    } else {
                        alert("Rename failed: " + (data.detail || "Unknown error"));
                        btn.disabled = false;
                        btn.querySelector("span").textContent = "Rename";
                    }
                } catch (err) {
                    alert("Network error during rename.");
                    btn.disabled = false;
                    btn.querySelector("span").textContent = "Rename";
                }
            });
        });

        // Download (S3 -> Local)
        document.querySelectorAll(".btn-download-local").forEach(btn => {
            btn.addEventListener("click", async () => {
                const url = btn.dataset.url;

                btn.disabled = true;
                btn.querySelector("span").textContent = "Downloading...";

                try {
                    const res = await fetch("/api/spreadsheet/download", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ url }),
                    });
                    const data = await res.json();
                    if (res.ok && data.success) {
                        showStatus("Download Complete", data.message, "var(--success-color)");
                        syncBtn.click();
                    } else {
                        alert("Download failed: " + (data.detail || "Unknown error"));
                        btn.disabled = false;
                        btn.querySelector("span").textContent = "Download";
                    }
                } catch (err) {
                    alert("Network error during download.");
                    btn.disabled = false;
                    btn.querySelector("span").textContent = "Download";
                }
            });
        });

        // Open Folder
        document.querySelectorAll(".btn-open-card-folder").forEach(btn => {
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
