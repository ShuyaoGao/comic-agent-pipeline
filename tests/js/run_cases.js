// 用 Node 跑 JS 版流水线（play/js/），把每个创意的全部产物输出成一个 JSON，供 tests/test_parity.py 与 Python 版比对。
//   node tests/js/run_cases.js tests/parity_cases.json > out.json
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const JS = path.resolve(__dirname, "..", "..", "play", "js");
const ctx = { console, TextEncoder };
ctx.globalThis = ctx;
vm.createContext(ctx);
for (const f of ["pyrt.js", "mock_llm.js", "pipeline.js", "presets.js"])
  vm.runInContext(fs.readFileSync(path.join(JS, f), "utf8"), ctx, { filename: f });
const { Pipeline, applyCostPreset } = ctx;

const spec = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = [];
for (const c of spec.cases) {
  const config = applyCostPreset(Pipeline.defaultConfig(), c.preset || "standard");
  config.seed = c.seed;
  const run = Pipeline.makeContext(config);
  const state = Pipeline.newState(c.idea, "parity", "-");
  Pipeline.runAll(state, run);
  out.push({
    idea: c.idea, seed: c.seed, preset: c.preset || "standard", config,
    state, genlog: run.genlog.records, summary: run.genlog.summary(),
    cost: Pipeline.estimateCost(state, run.genlog, config),
    dispatch: Pipeline.dispatchModels(state, config),
    library: Pipeline.buildAssetLibrary(state),
  });
}
process.stdout.write(JSON.stringify(out));
