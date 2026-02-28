const KEY = 'lyra_discoveries'

function load(): Set<string> {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? new Set(JSON.parse(raw)) : new Set()
  } catch {
    return new Set()
  }
}

export function addDiscoveries(ids: string[]): { newCount: number; total: number } {
  const set = load()
  const before = set.size
  for (const id of ids) {
    if (id) set.add(id)
  }
  if (set.size > before) {
    localStorage.setItem(KEY, JSON.stringify([...set]))
  }
  return { newCount: set.size - before, total: set.size }
}

export function getDiscoveryCount(): number {
  return load().size
}
