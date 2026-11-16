// The page's score weights must match the engine's (jobboard/rules/match.py), or the Match tab explains the
// score wrong. This test reads the Python file, so changing one side without the other fails here.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { SCORE_WEIGHTS } from "../js/core/constants.js";

test("score weights match the engine", () => {
  const py = readFileSync(new URL("../../jobboard/rules/match.py", import.meta.url), "utf8");
  const block = /WEIGHTS\s*=\s*\{([^}]*)\}/.exec(py)[1];
  const engine = Object.fromEntries([...block.matchAll(/"(\w+)":\s*([\d.]+)/g)].map(([, k, v]) => [k, Math.round(Number(v) * (Number(v) <= 1 ? 100 : 1))]));
  assert.deepEqual(engine, SCORE_WEIGHTS);
});
