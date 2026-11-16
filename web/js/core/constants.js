// Fixed lists the page uses. Change labels here and they change everywhere.

export const STATUSES = ["saved", "applied", "interviewing", "offer", "rejected", "withdrawn"];
export const STATUS_NAME = { saved: "Saved", applied: "Applied", interviewing: "Interviewing", offer: "Offer", rejected: "Rejected", withdrawn: "Withdrawn" };

// How the match score is made up (must match WEIGHTS in jobboard/rules/match.py).
export const SCORE_PARTS = { skills: "Skills", title: "Title", level: "Level", location: "Location", salary: "Pay" };
export const SCORE_WEIGHTS = { skills: 40, title: 25, level: 15, location: 12, salary: 8 };

// Filters as the server expects them; DEFAULT_FILTERS is "nothing filtered".
export const DEFAULT_FILTERS = { view: "recommended", q: "", work_model: "", min_score: "", days: "", sort: "score", salary: "", sponsor: "", no_clearance: "", max_commute: "" };

// Labels for the removable chips under the toolbar. Keys are the filters that live in the Filters panel.
export const FILTER_LABELS = {
  min_score: (v) => `${v}%+ match`,
  days: (v) => ({ 1: "Past 24 hours", 3: "Past 3 days", 7: "Past week", 30: "Past month" }[v] || `Past ${v} days`),
  max_commute: (v) => `Commute ≤ ${v} min`,
  salary: () => "Shows pay",
  no_clearance: () => "No clearance needed",
  sponsor: () => "Visa friendly",
};

// The screens, in sidebar order: [id, label, icon].
export const SCREENS = [["jobs", "Matches", "star"], ["tracker", "Applications", "board"], ["coach", "Coach", "bolt"], ["profile", "Profile", "people"], ["boards", "Job boards", "grid"]];

// Where commute directions start when your profile has no address (matches config.HOME on the server).
export const HOME_FALLBACK = "Suitland, MD 20746";

// A description shorter than this is treated as a snippet: the page offers "Get the full description".
export const SNIPPET_LENGTH = 1500;
