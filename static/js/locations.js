const POLL_INTERVAL_MS = 30000;

const container = document.getElementById("locations");
const searchInput = document.getElementById("location-search");
const searchEmpty = document.getElementById("location-search-empty");

// Fades from green at 0% to red at 100%. The bar stops growing at 100%, but
// the written percentage can go higher.
function renderCapacity(capacityEl, percent) {
    const filled = Math.min(percent, 100);
    const fill = capacityEl.querySelector(".capacity-fill");
    fill.style.width = `${filled}%`;
    fill.style.backgroundColor = `hsl(${120 * (1 - filled / 100)}, 75%, 40%)`;
    capacityEl.querySelector(".capacity-percent").textContent = `${percent}%`;
}

function renderStatus(statusEl, isOpen) {
    statusEl.textContent = isOpen ? "Open" : "Closed";
    statusEl.classList.toggle("open", isOpen);
    statusEl.classList.toggle("closed", !isOpen);
}

function renderHours(hoursEl, hours) {
    if (hours.length === 0) {
        hoursEl.textContent = "No hours listed.";
        return;
    }
    const table = document.createElement("table");
    for (const { day, hours: dayHours } of hours) {
        const row = table.insertRow();
        row.insertCell().textContent = day;
        row.insertCell().textContent = dayHours;
    }
    hoursEl.replaceChildren(table);
}

async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`${url} returned ${response.status}`);
    }
    return response.json();
}

async function toggleHours(location, button) {
    const hoursEl = location.querySelector(".location-hours");
    const expanded = hoursEl.hidden;
    hoursEl.hidden = !expanded;
    button.setAttribute("aria-expanded", expanded);
    button.textContent = expanded ? "Less info" : "More info";

    if (expanded && !hoursEl.dataset.loaded) {
        hoursEl.textContent = "Loading hours...";
        try {
            renderHours(hoursEl, await fetchJson(location.dataset.hoursUrl));
            hoursEl.dataset.loaded = "true";
        } catch (error) {
            console.error(error);
            hoursEl.textContent = "Could not load hours.";
        }
    }
}

// Keeps the page live. A failed poll leaves the last values on screen until
// the next one succeeds.
async function refreshStatus() {
    if (document.hidden) {
        return;
    }
    try {
        const statuses = await fetchJson(container.dataset.statusUrl);
        for (const { location_id, percent_full, is_open_now } of statuses) {
            const location = container.querySelector(`[data-location-id="${location_id}"]`);
            if (location) {
                renderCapacity(location.querySelector(".capacity"), percent_full);
                renderStatus(location.querySelector(".status"), is_open_now);
            }
        }
    } catch (error) {
        console.error(error);
    }
}

// Shows locations whose name or address contains the search text, and hides
// any address group left with nothing to show.
function applySearch() {
    const query = searchInput.value.trim().toLowerCase();
    let anyVisible = false;

    container.querySelectorAll(".location-group").forEach((group) => {
        const address = group.querySelector("h3").textContent.toLowerCase();
        let groupVisible = false;

        group.querySelectorAll(".location").forEach((location) => {
            const name = location.querySelector(".location-name").textContent.toLowerCase();
            const matches = name.includes(query) || address.includes(query);
            location.hidden = !matches;
            groupVisible = groupVisible || matches;
        });

        group.hidden = !groupVisible;
        anyVisible = anyVisible || groupVisible;
    });

    // Only applies when there are locations to search, since the page has its
    // own message for an empty list.
    searchEmpty.hidden = anyVisible || container.querySelector(".location-group") === null;
}

searchInput.addEventListener("input", applySearch);
applySearch(); // The browser may restore the search text on reload.

container.querySelectorAll(".capacity").forEach((capacityEl) => {
    renderCapacity(capacityEl, Number(capacityEl.dataset.percent));
});

container.addEventListener("click", (event) => {
    const button = event.target.closest(".more-info");
    if (button) {
        toggleHours(button.closest(".location"), button);
    }
});

setInterval(refreshStatus, POLL_INTERVAL_MS);
