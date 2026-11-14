const container = document.getElementById("activities");
const searchInput = document.getElementById("activity-search");
const searchEmpty = document.getElementById("activity-search-empty");

// Shows activities whose name, group or location contains the search text.
function applySearch() {
    const query = searchInput.value.trim().toLowerCase();
    const activities = container.querySelectorAll(".activity");
    let anyVisible = false;

    activities.forEach((activity) => {
        const matches = activity.dataset.search.includes(query);
        activity.hidden = !matches;
        anyVisible = anyVisible || matches;
    });

    // The page has its own message when there are no activities at all.
    searchEmpty.hidden = anyVisible || activities.length === 0;
}

searchInput.addEventListener("input", applySearch);
applySearch(); // The browser may restore the search text on reload.

container.addEventListener("click", (event) => {
    const button = event.target.closest(".view-description");
    if (!button) {
        return;
    }
    const details = button.closest(".activity").querySelector(".activity-details");
    const expanded = details.hidden;
    details.hidden = !expanded;
    button.setAttribute("aria-expanded", expanded);
    button.textContent = expanded ? "Hide description" : "View description";
});
