// Registers this bundle's skills on the skill registry of the preset that mounts it.
// Zero dependencies: reads skills/*/SKILL.md next to this file and calls ctx.skills.register().
//
// `source` is NOT optional in practice. The registry never validates a runtime
// registration at register() time, but every later `skills.get(name)` runs
// validateDefinition(), which throws `source must be a string` when it is
// missing -- the skill then lists fine and fails only when the model loads it.
// Both runtime registrations shipped with the Harness (`dsh-ppt`, the Windows
// ACL diagnosis skill) set it. Never drop this field.
import { readdirSync, readFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

export const name = 'dsh-rollback-recovery-skills'
export const inject = ['skills']

const root = join(dirname(fileURLToPath(import.meta.url)), 'skills')

function parse (text) {
  const m = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/.exec(text)
  if (!m) return null
  const meta = {}
  for (const line of m[1].split('\n')) {
    const i = line.indexOf(':')
    if (i < 0) continue
    const k = line.slice(0, i).trim(); let v = line.slice(i + 1).trim()
    if (v.startsWith('"')) { try { v = JSON.parse(v) } catch {} }
    meta[k] = v
  }
  return { meta, body: m[2] }
}

export function apply (ctx) {
  if (!existsSync(root)) return
  for (const dir of readdirSync(root, { withFileTypes: true })) {
    if (!dir.isDirectory()) continue
    const file = join(root, dir.name, 'SKILL.md')
    if (!existsSync(file)) continue
    const parsed = parse(readFileSync(file, 'utf8'))
    if (!parsed || !parsed.meta.name || !parsed.meta.description) {
      ctx.logger?.warn?.('dsh-rollback-recovery-skills: ' + dir.name + ': SKILL.md 缺 name/description，已跳过')
      continue
    }
    try {
      ctx.skills.register({
        name: parsed.meta.name,
        description: parsed.meta.description,
        source: 'bundle',
        content: parsed.body,
        resourceBase: { kind: 'directory', path: join(root, dir.name) }
      })
    } catch (err) {
      ctx.logger?.warn?.('dsh-rollback-recovery-skills: ' + dir.name + ': ' + (err?.message ?? err))
    }
  }
}
