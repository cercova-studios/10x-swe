import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import plugin from '../plugins/10x-swe/index.js';

test('registers canonical content without replacing user skills or agents', async () => {
  const skills = new Map([['diagnose', { id: 'diagnose', content: 'user skill' }]]);
  const permissions = [{ action: '*', resource: '*', effect: 'ask' }];
  const agents = new Map([
    ['build', { permissions }], ['code-reviewer', { system: 'user agent' }],
  ]);
  const commands = new Map();
  const prompts = [];
  await plugin.setup({
    skill: { transform: async (fn) => fn({ get: (id) => skills.get(id), add: (s) => skills.set(s.id, s) }) },
    agent: { transform: async (fn) => fn({
      get: (id) => agents.get(id),
      update(id, update) { const agent = {}; update(agent); agents.set(id, agent); },
    }) },
    command: { list: async () => ({ data: [] }), transform: async (fn) => fn({ add: (c) => commands.set(c.name, c) }) },
    session: { prompt: async (prompt) => prompts.push(prompt) },
  });
  assert.equal(skills.get('diagnose').content, 'user skill');
  assert.equal(agents.get('code-reviewer').system, 'user agent');
  const data = JSON.parse(await readFile(new URL('../plugins/10x-swe/opencode-data.json', import.meta.url)));
  assert.equal(skills.size, data.skills.length);
  assert.equal(agents.size, data.agents.length + 1);
  assert.equal(commands.size, data.commands.length);
  for (const skill of skills.values()) {
    if (skill.id === 'diagnose') continue;
    assert.ok(skill.content.length > 0);
    assert.ok(skill.path.startsWith('/'));
    assert.ok(!skill.content.startsWith('---'));
  }
  for (const [id, agent] of agents) {
    if (id === 'build' || id === 'code-reviewer') continue;
    assert.equal(agent.mode, 'subagent');
    assert.deepEqual(agent.permissions, permissions);
    assert.notEqual(agent.permissions, permissions);
    assert.equal(agent.model, undefined);
  }
  const prompt = { text: 'literal $& and $ARGUMENTS', files: [{ uri: 'file:///tmp/input' }] };
  await commands.get('10x-swe:research').execute({ sessionID: 'session', prompt, delivery: 'queue' });
  assert.equal(prompts[0].text.trim(), `Invoke the code-research skill for: ${prompt.text}`);
  assert.equal(prompts[0].files, prompt.files);
  assert.equal(prompts[0].delivery, 'queue');
  assert.equal(prompts[0].sessionID, 'session');
});

test('missing build agent requires approval and existing commands survive', async () => {
  const agents = [];
  const commands = [];
  await plugin.setup({
    skill: { transform: async () => {} },
    agent: { transform: async (fn) => fn({
      get: () => undefined,
      update(id, update) { const agent = { id }; update(agent); agents.push(agent); },
    }) },
    command: {
      list: async () => ({ data: [{ name: '10x-swe:research' }] }),
      transform: async (fn) => fn({ add: (command) => commands.push(command) }),
    },
  });
  assert.ok(agents.length > 0);
  for (const agent of agents) assert.deepEqual(agent.permissions, [{ action: '*', resource: '*', effect: 'ask' }]);
  assert.ok(!commands.some((command) => command.name === '10x-swe:research'));
});
