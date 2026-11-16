// Unit tests for the page's pure helpers. Run: node --test web/tests/
import assert from "node:assert/strict";
import { test } from "node:test";
import { ago, cap, isHourly, pay, place, plural, scoreBand } from "../js/core/format.js";
import { DEFAULT_FILTERS, FILTER_LABELS, SCORE_PARTS, SCORE_WEIGHTS, STATUSES, STATUS_NAME } from "../js/core/constants.js";

test("pay shows hourly and yearly ranges the way job posts do", () => {
  assert.equal(pay({ salary_min: 39520, salary_max: 41600, salary_text: "$19 - $20 an hour" }), "$19–$20/hr");
  assert.equal(pay({ salary_min: 45000, salary_max: 52000 }), "$45K–$52K");
  assert.equal(pay({ salary_min: 40000, salary_max: 40000 }), "$40K");
  assert.equal(pay({ salary_min: 37440, salary_max: 37440 }), "$18/hr");    // an exact hourly rate, said yearly
  assert.equal(pay({}), "");
  assert.equal(isHourly({ salary_text: "per hour" }), true);
});

test("ago and plural read naturally", () => {
  const now = new Date("2026-11-13T12:00:00").getTime();
  assert.equal(ago("2026-11-13", now), "Today");
  assert.equal(ago("2026-11-12", now), "1 day ago");
  assert.equal(ago("2026-11-08", now), "5 days ago");
  assert.equal(ago("2026-09-01", now), "2 mo ago");
  assert.equal(ago("", now), "");
  assert.equal(plural(1, "job"), "1 job");
  assert.equal(plural(3, "match", "matches"), "3 matches");
});

test("place says remote or where, and on-site plainly", () => {
  assert.equal(place({ work_model: "remote", location: "Anywhere" }), "Remote");
  assert.equal(place({ work_model: "remote", location: "Tampa, FL" }), "Remote · Tampa, FL");
  assert.equal(place({ work_model: "onsite", location: "Washington DC" }), "On-site · Washington DC");
  assert.equal(place({ work_model: "unknown", location: "Washington DC" }), "Washington DC");
  assert.equal(place({ work_model: "hybrid", location: "" }), "Hybrid");
  assert.equal(cap("remote"), "Remote");
});

test("score bands match the colours", () => {
  assert.equal(scoreBand(85), "");
  assert.equal(scoreBand(70), "good");
  assert.equal(scoreBand(55), "fair");
  assert.equal(scoreBand(20), "weak");
});

test("constants agree with each other", () => {
  assert.deepEqual(Object.keys(SCORE_PARTS), Object.keys(SCORE_WEIGHTS));
  assert.equal(Object.values(SCORE_WEIGHTS).reduce((a, b) => a + b, 0), 100);
  for (const s of STATUSES) assert.ok(STATUS_NAME[s], s);
  for (const key of Object.keys(FILTER_LABELS)) assert.ok(key in DEFAULT_FILTERS, key);
});
