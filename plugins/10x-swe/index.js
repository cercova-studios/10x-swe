import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

// OpenCode v2 accepts this definition directly; no runtime dependency is needed.
export default {
  id: 'cercova.10x-swe',
  async setup(ctx) {
    const data = JSON.parse(await readFile(new URL('./opencode-data.json', import.meta.url), 'utf8'));
    const skills = await Promise.all(data.skills.map(async ({ path, ...skill }) => {
      const file = new URL(path, import.meta.url);
      const markdown = await readFile(file, 'utf8');
      const end = markdown.indexOf('\n---\n', 4);
      if (!markdown.startsWith('---\n') || end < 0) throw new Error(`Invalid skill frontmatter: ${path}`);
      return { ...skill, path: fileURLToPath(file), content: markdown.slice(end + 5) };
    }));
    await ctx.skill.transform((editor) => {
      for (const skill of skills) if (!editor.get(skill.id)) editor.add(skill);
    });
    await ctx.agent.transform((editor) => {
      for (const source of data.agents) {
        if (editor.get(source.name)) continue;
        const permissions = editor.get('build')?.permissions;
        editor.update(source.name, (agent) => {
          agent.name = source.name;
          agent.description = source.description;
          agent.system = source.content;
          agent.mode = 'subagent';
          agent.permissions = structuredClone(permissions ?? [{ action: '*', resource: '*', effect: 'ask' }]);
        });
      }
    });
    const existingCommands = new Set((await ctx.command.list()).data.map((command) => command.name));
    await ctx.command.transform((editor) => {
      for (const command of data.commands) {
        if (existingCommands.has(`10x-swe:${command.name}`)) continue;
        editor.add({
          name: `10x-swe:${command.name}`,
          description: command.description,
          async execute({ sessionID, prompt, delivery }) {
            await ctx.session.prompt({
              ...prompt, sessionID, delivery,
              text: command.content.replaceAll('$ARGUMENTS', () => prompt.text ?? ''),
            });
          },
        });
      }
    });
  },
};
