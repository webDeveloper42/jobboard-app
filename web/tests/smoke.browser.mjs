// Browser smoke test for the Jobs page (laptop and desktop sizes): every screen and job tab renders without errors, keyboard shortcuts work,
// and every class the page uses has a style (catches BEM typos between js/ and css/).
//
// Run it with `./dev browser` from the repo root (it starts a throwaway copy of the dashboard on your data copy).
// Needs puppeteer-core and a headless Chrome; set PUPPETEER_DIR and CHROME if yours live elsewhere.
//   node web/tests/smoke.browser.mjs http://127.0.0.1:8899/jobs/ [screenshots-folder]
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const HOME = process.env.HOME;
const PUPPETEER = process.env.PUPPETEER_DIR || `${HOME}/docs-app/tests/js/node_modules/puppeteer-core`;
const CHROME = process.env.CHROME || `${HOME}/docs-app/tests/js/browsers/chrome-headless-shell/linux-157.0.8103.50/chrome-headless-shell-linux64/chrome-headless-shell`;
const URL = process.argv[2] || "http://127.0.0.1:8899/jobs/";
const SHOTS = process.argv[3] || null;
const ALLOWED_UNSTYLED = new Set(["ic"]);   // classes that come from elsewhere (the shared icon set)

const puppeteer = require(PUPPETEER);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const problems = [];
const seenClasses = new Set();

async function collectClasses(page) {
  for (const c of await page.evaluate(() => [...document.querySelectorAll("[class]")].flatMap((el) => [...el.classList]))) seenClasses.add(c);
}
async function shot(page, name) { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png` }); }
async function clickText(page, selector, re) {
  const ok = await page.evaluate((sel, src) => { const el = [...document.querySelectorAll(sel)].find((x) => new RegExp(src).test(x.textContent)); if (el) el.click(); return Boolean(el); }, selector, re.source);
  if (!ok) problems.push(`couldn't find ${selector} matching ${re}`);
  await wait(900);
}

const browser = await puppeteer.launch({ executablePath: CHROME, args: ["--no-sandbox"] });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });   // desktop; a laptop check at 1280x800 runs at the end
  page.on("pageerror", (e) => problems.push(`page error: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });
  page.on("response", (r) => { if (r.status() >= 400 && r.url().includes("/jobs/")) problems.push(`HTTP ${r.status()} ${r.url()}`); });
  await page.goto(URL, { waitUntil: "networkidle0" });
  await page.evaluate(() => { localStorage.clear(); localStorage.setItem("jobs-screen", "jobs"); });
  await page.goto(URL, { waitUntil: "networkidle0" });
  await wait(600);
  await collectClasses(page); await shot(page, "1-matches");

  // keyboard: j opens the first job, then each tab renders
  await page.keyboard.press("j"); await wait(1200);
  if (!(await page.$(".job-detail"))) problems.push("pressing j didn't open a job");
  for (const tab of ["Match", "Apply kit", "Ask Coach", "Overview"]) {
    await clickText(page, ".tabs__tab", new RegExp(`^${tab}`));
    await collectClasses(page); await shot(page, `2-tab-${tab.toLowerCase().replace(/\s+/g, "-")}`);
  }
  await page.click(".menu__toggle"); await wait(300); await collectClasses(page);
  await page.keyboard.press("Escape");

  // filters panel and chips
  await clickText(page, ".toolbar .button", /Filters/);
  await page.evaluate(() => document.querySelector(".filter-panel .checkbox__input")?.click()); await wait(1200);
  await collectClasses(page); await shot(page, "3-filters");
  await clickText(page, ".active-filters .link-button", /Clear all/);

  // shortcuts dialog
  await page.keyboard.press("?"); await wait(300);
  if (!(await page.evaluate(() => document.getElementById("dialog").open))) problems.push("? didn't open the shortcuts");
  await collectClasses(page);
  await page.keyboard.press("Escape"); await wait(200);

  // the other screens
  for (const [label, name] of [["Applications", "4-applications"], ["Coach", "5-coach"], ["Profile", "6-profile"], ["Job boards", "7-boards"]]) {
    await clickText(page, ".nav-item", new RegExp(`^${label}`));
    await wait(500); await collectClasses(page); await shot(page, name);
  }

  // laptop width: nothing should stick out sideways
  await page.setViewport({ width: 1280, height: 800 });
  await clickText(page, ".nav-item", /^Matches/);
  await page.keyboard.press("j"); await wait(1000);
  if (await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)) problems.push("laptop: the page scrolls sideways");
  await shot(page, "8-laptop");

  // every class used must be styled somewhere
  const styled = new Set(await page.evaluate(() => {
    const out = [];
    const walk = (sheet) => { for (const rule of sheet.cssRules) { if (rule.styleSheet) walk(rule.styleSheet); else if (rule.cssRules) walk(rule); if (rule.selectorText) out.push(...(rule.selectorText.match(/\.[A-Za-z_][\w-]*/g) || []).map((s) => s.slice(1))); } };
    for (const s of document.styleSheets) walk(s);
    return out;
  }));
  const unstyled = [...seenClasses].filter((c) => !styled.has(c) && !ALLOWED_UNSTYLED.has(c)).sort();
  if (unstyled.length) problems.push(`classes with no styles: ${unstyled.join(", ")}`);
} finally {
  await browser.close();
}
if (problems.length) { console.log("FAIL\n- " + problems.join("\n- ")); process.exit(1); }
console.log(`OK: ${seenClasses.size} classes used, all styled; no errors.`);
