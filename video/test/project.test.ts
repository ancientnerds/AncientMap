import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const read = (name: string) => JSON.parse(readFileSync(fileURLToPath(new URL(`../${name}`, import.meta.url)), 'utf-8'))
const pkg = read('package.json') as { dependencies: Record<string, string>; devDependencies: Record<string, string> }
const deps = { ...pkg.dependencies, ...pkg.devDependencies }
const isRemotion = (name: string) => name === 'remotion' || name.startsWith('@remotion/')

describe('video/package.json (spec 4.8: Remotion 4.0.529, every @remotion/* at the same exact version)', () => {
  it('declares remotion and the five @remotion packages the renderer uses, all at exactly 4.0.529', () => {
    const remotion = Object.keys(deps).filter(isRemotion).sort()
    expect(remotion).toEqual(['@remotion/bundler', '@remotion/cli', '@remotion/fonts', '@remotion/media', '@remotion/renderer', 'remotion'])
    for (const name of remotion) expect(deps[name], name).toBe('4.0.529')
  })
  it('pins every other dependency to an exact version', () => {
    for (const [name, version] of Object.entries(deps)) expect(version, name).toMatch(/^\d+\.\d+\.\d+$/)
  })
  it('locks every installed remotion package, transitive ones included, at 4.0.529', () => {
    const lock = read('package-lock.json') as { packages: Record<string, { version?: string }> }
    const locked = Object.entries(lock.packages).filter(([key]) => isRemotion(key.replace(/^.*node_modules\//, '')))
    expect(locked.length).toBeGreaterThan(6)
    for (const [key, entry] of locked) expect(entry.version, key).toBe('4.0.529')
  })
})
