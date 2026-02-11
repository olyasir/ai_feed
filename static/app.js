document.addEventListener("DOMContentLoaded", () => {
    const feed = document.getElementById("feed");
    const refreshBtn = document.getElementById("refresh-btn");
    const statusBar = document.getElementById("status-bar");
    const sortSelect = document.getElementById("sort-select");

    let activeSource = "all";
    let activeTopic = "all";

    // Source filter buttons
    document.querySelectorAll(".filter-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            activeSource = btn.dataset.source;
            applyFilters();
        });
    });

    // Topic filter pills
    document.querySelectorAll(".topic-pill").forEach(pill => {
        pill.addEventListener("click", () => {
            document.querySelectorAll(".topic-pill").forEach(p => p.classList.remove("active"));
            pill.classList.add("active");
            activeTopic = pill.dataset.topic;
            applyFilters();
        });
    });

    function applyFilters() {
        document.querySelectorAll(".card").forEach(card => {
            const source = card.dataset.source || "";
            const tags = (card.dataset.tags || "").split(",").filter(Boolean);

            // Source filter
            let sourceMatch = activeSource === "all";
            if (!sourceMatch) {
                if (activeSource === "blog") {
                    // "Blogs" matches anything that isn't Arxiv, Reddit, or HN
                    sourceMatch = source !== "Arxiv"
                        && !source.startsWith("r/")
                        && source !== "Hacker News";
                } else if (activeSource === "reddit") {
                    sourceMatch = source.startsWith("r/");
                } else {
                    sourceMatch = source === activeSource;
                }
            }

            // Topic filter
            let topicMatch = activeTopic === "all" || tags.includes(activeTopic);

            card.classList.toggle("hidden-by-source", !sourceMatch);
            card.classList.toggle("hidden-by-topic", !topicMatch);
        });
    }

    // Sort
    sortSelect.addEventListener("change", () => {
        window.location.href = "/?sort=" + sortSelect.value;
    });

    // Refresh
    refreshBtn.addEventListener("click", async () => {
        refreshBtn.classList.add("loading");
        refreshBtn.disabled = true;
        statusBar.className = "status-bar";
        statusBar.textContent = "Fetching from all sources...";

        try {
            const resp = await fetch("/api/fetch", { method: "POST" });
            const data = await resp.json();

            if (data.total_new > 0) {
                statusBar.className = "status-bar success";
                statusBar.textContent = `Found ${data.total_new} new article(s). Reloading...`;
                setTimeout(() => window.location.reload(), 1000);
            } else {
                statusBar.className = "status-bar";
                statusBar.textContent = "No new articles found.";

                // Show per-source details
                const details = Object.entries(data.sources || {})
                    .map(([src, info]) => {
                        if (info.status === "skipped") return `${src}: skipped (${info.reason})`;
                        if (info.status === "error") return `${src}: error`;
                        return `${src}: ${info.fetched} fetched, ${info.relevant} relevant`;
                    })
                    .join(" | ");
                if (details) {
                    statusBar.textContent += " " + details;
                }

                setTimeout(() => { statusBar.className = "status-bar hidden"; }, 8000);
            }
        } catch (err) {
            statusBar.className = "status-bar error";
            statusBar.textContent = "Fetch failed: " + err.message;
        } finally {
            refreshBtn.classList.remove("loading");
            refreshBtn.disabled = false;
        }
    });

    // Mark as read on click
    document.addEventListener("click", async (e) => {
        const link = e.target.closest("a[data-article-id]");
        if (!link) return;

        const articleId = link.dataset.articleId;
        const card = link.closest(".card");
        if (card) card.classList.add("read");

        try {
            await fetch(`/api/read/${articleId}`, { method: "POST" });
        } catch (err) {
            // Silently ignore — the visual state is already updated
        }
    });
});
