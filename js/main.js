const PACKAGE = {
    tracking: "871172274092",
    shipDate: "2026-04-28",
    deliveryDate: "2026-04-29",
    origin: "Dothan, AL",
    destination: "Tuscaloosa, AL",
};

const EXPECTED_STEPS = [
    { key: "picked_up", title: "Picked up", location: "FedEx Office, Dothan, AL", date: "2026-04-28" },
    { key: "origin", title: "Departed origin facility", location: "Dothan, AL", date: "2026-04-28" },
    { key: "hub", title: "Arrived at FedEx hub", location: "Memphis, TN (likely)", date: "2026-04-28" },
    { key: "out_hub", title: "Departed hub", location: "Memphis, TN (likely)", date: "2026-04-29" },
    { key: "destination", title: "Arrived at destination station", location: "Tuscaloosa, AL", date: "2026-04-29" },
    { key: "out_for_delivery", title: "Out for delivery", location: "Tuscaloosa, AL", date: "2026-04-29" },
    { key: "delivered", title: "Delivered", location: "3431 Firethorn Drive, Tuscaloosa, AL", date: "2026-04-29" },
];

const STEPS_KEY = `tracker:${PACKAGE.tracking}:steps`;
const LOG_KEY = `tracker:${PACKAGE.tracking}:log`;

function loadJSON(key, fallback) {
    try {
        const raw = localStorage.getItem(key);
        return raw ? JSON.parse(raw) : fallback;
    } catch {
        return fallback;
    }
}

function saveJSON(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
}

function todayISO() {
    return new Date().toISOString().slice(0, 10);
}

function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

function renderTimeline() {
    const stepState = loadJSON(STEPS_KEY, {});
    const list = document.getElementById("timeline");
    list.innerHTML = "";

    const lastDoneIdx = EXPECTED_STEPS.reduce(
        (acc, step, i) => (stepState[step.key] ? i : acc),
        -1
    );

    EXPECTED_STEPS.forEach((step, i) => {
        const li = document.createElement("li");
        li.className = "timeline-step";
        if (stepState[step.key]) li.classList.add("done");
        else if (i === lastDoneIdx + 1) li.classList.add("current");

        const checkedAt = stepState[step.key];
        li.innerHTML = `
            <div class="step-title">${step.title}</div>
            <div class="step-meta">${step.location} · expected ${formatDate(step.date)}${
            checkedAt ? ` · ✓ confirmed ${formatDate(checkedAt)}` : ""
        }</div>
        `;
        li.addEventListener("click", () => {
            const next = { ...loadJSON(STEPS_KEY, {}) };
            if (next[step.key]) delete next[step.key];
            else next[step.key] = todayISO();
            saveJSON(STEPS_KEY, next);
            renderTimeline();
            renderStatusBanner();
        });
        list.appendChild(li);
    });
}

function renderStatusBanner() {
    const stepState = loadJSON(STEPS_KEY, {});
    const banner = document.getElementById("status-banner");
    const lastDone = [...EXPECTED_STEPS].reverse().find((s) => stepState[s.key]);
    if (!lastDone) {
        banner.textContent = "No status confirmed yet — check FedEx for live updates.";
        banner.style.color = "var(--color-warn)";
        return;
    }
    if (lastDone.key === "delivered") {
        banner.textContent = `Delivered · ${formatDate(stepState[lastDone.key])}`;
        banner.style.color = "var(--color-accent)";
        return;
    }
    banner.textContent = `Last confirmed: ${lastDone.title} · ${lastDone.location}`;
    banner.style.color = "var(--color-accent)";
}

function renderLog() {
    const entries = loadJSON(LOG_KEY, []);
    const list = document.getElementById("log-entries");
    list.innerHTML = "";

    if (entries.length === 0) {
        const li = document.createElement("li");
        li.className = "empty-log";
        li.textContent = "No log entries yet. Add your first daily check-in above.";
        list.appendChild(li);
        return;
    }

    entries
        .slice()
        .sort((a, b) => b.date.localeCompare(a.date))
        .forEach((entry) => {
            const li = document.createElement("li");
            li.className = "log-entry";
            li.innerHTML = `
                <div>
                    <div class="log-entry-date">${formatDate(entry.date)}</div>
                    <div class="log-entry-location"></div>
                </div>
                <button class="log-entry-delete" type="button" data-id="${entry.id}">Remove</button>
                ${entry.note ? `<div class="log-entry-note"></div>` : ""}
            `;
            li.querySelector(".log-entry-location").textContent = entry.location;
            const noteEl = li.querySelector(".log-entry-note");
            if (noteEl) noteEl.textContent = entry.note;
            list.appendChild(li);
        });

    list.querySelectorAll(".log-entry-delete").forEach((btn) => {
        btn.addEventListener("click", () => {
            const id = btn.getAttribute("data-id");
            const next = loadJSON(LOG_KEY, []).filter((e) => e.id !== id);
            saveJSON(LOG_KEY, next);
            renderLog();
        });
    });
}

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("log-date").value = todayISO();

    renderTimeline();
    renderStatusBanner();
    renderLog();

    document.getElementById("log-form").addEventListener("submit", (e) => {
        e.preventDefault();
        const date = document.getElementById("log-date").value;
        const location = document.getElementById("log-location").value.trim();
        const note = document.getElementById("log-note").value.trim();
        if (!date || !location) return;

        const entries = loadJSON(LOG_KEY, []);
        entries.push({
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
            date,
            location,
            note,
        });
        saveJSON(LOG_KEY, entries);

        document.getElementById("log-location").value = "";
        document.getElementById("log-note").value = "";
        document.getElementById("log-date").value = todayISO();
        renderLog();
    });

    document.getElementById("log-clear").addEventListener("click", () => {
        if (!confirm("Clear all log entries for this package?")) return;
        saveJSON(LOG_KEY, []);
        renderLog();
    });

    document.getElementById("copy-tracking").addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(PACKAGE.tracking);
            const btn = document.getElementById("copy-tracking");
            const original = btn.textContent;
            btn.textContent = "Copied!";
            setTimeout(() => (btn.textContent = original), 1500);
        } catch {
            alert(`Tracking #: ${PACKAGE.tracking}`);
        }
    });
});
