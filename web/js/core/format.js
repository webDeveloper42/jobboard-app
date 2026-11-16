// Turning job data into text. No DOM here, so these run (and are tested) in Node too: node --test web/tests/

const HOURS_PER_YEAR = 2080;

export const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");

/** True when a job's pay is hourly (said so, or a yearly figure that's an exact hourly rate). */
export function isHourly(job) {
  if (/\b(hr|hour|hourly)\b|\/h\b/i.test(job.salary_text || "")) return true;
  return Boolean(job.salary_max && job.salary_max <= 150000 && job.salary_min % HOURS_PER_YEAR === 0 && job.salary_max % HOURS_PER_YEAR === 0);
}

function money(n, hourly) {
  if (hourly) return `$${(n / HOURS_PER_YEAR).toFixed(n % HOURS_PER_YEAR ? 2 : 0).replace(/\.00$/, "")}`;
  return `$${Math.round(n / 1000)}K`;
}

/** "$19–$20/hr", "$45K–$52K", "$40K", or "" when the post gives no pay. */
export function pay(job) {
  if (!job.salary_min) return "";
  const hourly = isHourly(job);
  const low = money(job.salary_min, hourly);
  const high = job.salary_max && job.salary_max !== job.salary_min ? money(job.salary_max, hourly) : "";
  return (high ? `${low}–${high}` : low) + (hourly ? "/hr" : "");
}

/** "Today", "1 day ago", "5 days ago", "2 mo ago" for a 'YYYY-MM-DD' or ISO time. */
export function ago(stamp, now = Date.now()) {
  if (!stamp) return "";
  const days = Math.floor((now - new Date(stamp.length <= 10 ? `${stamp}T12:00` : stamp)) / 864e5);
  if (days <= 0) return "Today";
  if (days === 1) return "1 day ago";
  if (days < 30) return `${days} days ago`;
  if (days < 365) return `${Math.floor(days / 30)} mo ago`;
  return `${Math.floor(days / 365)} yr ago`;
}

/** "Nov 13" for a 'YYYY-MM-DD' date. */
export function dayLabel(date) {
  if (!date) return "";
  return new Date(`${date}T12:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** "Remote", "Remote · Tampa, FL", "On-site · Washington DC". */
export function place(job) {
  if (job.work_model === "remote") {
    return job.location && !/^(remote|anywhere|united states)$/i.test(job.location) ? `Remote · ${job.location}` : "Remote";
  }
  const model = { unknown: "", onsite: "On-site" }[job.work_model] ?? cap(job.work_model || "");
  return [model, job.location].filter(Boolean).join(" · ");
}

/** The colour band a match score falls in: "" (strong), "good", "fair" or "weak". */
export const scoreBand = (value) => (value >= 80 ? "" : value >= 65 ? "good" : value >= 50 ? "fair" : "weak");

export const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;
