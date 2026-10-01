/**
 * Runs one .claude/workflows/*.js script against canned agent answers and prints what it did.
 *
 *   node workflow_harness.mjs <workflow.js> <scenario.json>
 *
 * A workflow is the body of an async function with `args`, `agent`, `pipeline`, `phase` and
 * `log` in scope and a top-level `return`, which `node --check` refuses, so the file is wrapped
 * as one (its `export const meta` becomes a plain const). The scenario answers each agent call
 * by its label:
 *   {"args": {...}, "answers": {"<label>": <structured answer> | null, ...}}
 * An agent whose label has no answer fails the run: a test lists every call the script makes.
 * Output on stdout, one JSON object: {result, prompts: [{label, prompt}], logs, error}.
 */
import { readFileSync } from 'node:fs'

const [, , file, scenarioPath] = process.argv
const scenario = JSON.parse(readFileSync(scenarioPath, 'utf8'))
const source = readFileSync(file, 'utf8').replace(/^export const meta = /m, 'const meta = ')
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor

const prompts = []
const logs = []

async function agent(prompt, options) {
  prompts.push({ label: options.label, prompt })
  if (!(options.label in scenario.answers)) throw new Error(`the scenario has no answer for the agent "${options.label}"`)
  const answer = scenario.answers[options.label]
  return answer === null ? null : structuredClone(answer)
}

// pipeline(items, stage1, stage2, ...): each item runs the stages in order, a stage gets
// (previous stage's result, item); a stage that throws leaves the item's result null.
async function pipeline(items, ...stages) {
  const results = []
  for (const item of items) {
    let previous
    try {
      for (const stage of stages) previous = await stage(previous, item)
      results.push(previous)
    } catch {
      results.push(null)
    }
  }
  return results
}

const output = { result: null, prompts, logs, error: null }
try {
  const run = new AsyncFunction('args', 'agent', 'pipeline', 'phase', 'log', source)
  output.result = (await run(scenario.args, agent, pipeline, () => {}, (line) => logs.push(line))) ?? null
} catch (error) {
  output.error = error instanceof Error ? error.message : String(error)
}
process.stdout.write(JSON.stringify(output))
