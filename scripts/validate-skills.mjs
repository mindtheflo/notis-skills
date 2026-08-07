import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';

const root = new URL('../skills/', import.meta.url);
const entries = (await readdir(root, { withFileTypes: true }))
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort();

if (entries.length === 0) throw new Error('No skills found');

const names = new Set();
for (const directory of entries) {
  const path = join(root.pathname, directory, 'SKILL.md');
  const content = await readFile(path, 'utf8');
  const match = content.match(/^---\n([\s\S]*?)\n---\n/);
  if (!match) throw new Error(`${directory}: missing YAML frontmatter`);
  const name = match[1].match(/^name:\s*(.+)$/m)?.[1]?.trim();
  const description = match[1].match(/^description:\s*(.+)$/m)?.[1]?.trim();
  if (!name) throw new Error(`${directory}: missing name`);
  if (!description) throw new Error(`${directory}: missing description`);
  if (name !== directory) throw new Error(`${directory}: frontmatter name is ${name}`);
  if (names.has(name)) throw new Error(`${directory}: duplicate skill name`);
  names.add(name);
}

console.log(`Validated ${names.size} skills: ${[...names].join(', ')}`);
