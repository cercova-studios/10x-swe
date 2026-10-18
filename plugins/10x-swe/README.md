# 10x-swe

A terminal-first agent plugin with skills for software engineering, debugging,
architecture and development workflows.

## Install and try it

Install from your terminal with Claude Code available:

```sh
claude plugin marketplace add cercova-studios/10x-swe
claude plugin install 10x-swe@10x-swe
claude plugin list
```

The default install scope is your user account across projects. Add `--scope local`
to the install command for only the current repository. See the
[canonical setup guide](../../README.md#engineering-skills-only) for version guidance
and activation checks. The engineering workflows need only your agent and the tools
required by your task; the knowledge CLI build and playground are separate options.

Start a new Claude Code session in your project. Type `/10x-swe:diagnose` to check
that the skill appears, then choose a first task:

- Debug a failure: `/10x-swe:diagnose npm test fails on parser.spec.ts. Reproduce it, identify the cause, and verify the smallest fix.`
- Refactor safely: `/10x-swe:refactor Simplify the changed parser code while preserving its behavior and tests.`
- Review a change: `Use the 10x-swe:code-reviewer agent to review my current git diff against AGENTS.md. Report actionable findings with file locations.`

Expect a reproduced failure and regression evidence for diagnosis, behavior checks
for refactoring, or scoped findings for review. These are agent instructions;
loading a skill does not execute or verify the task by itself.

## Skills

### Workflow & Process
| Skill | Description |
|-------|-------------|
| [diagnose](skills/diagnose/SKILL.md) | Reproduce a bug, test hypotheses, and verify the smallest fix |
| [deep-architecture-analysis](skills/deep-architecture-analysis/SKILL.md) | Inspect a codebase through parallel architecture perspectives |
| [grill-me](skills/grill-me/SKILL.md) | Stress-test an idea through focused questions |
| [grill-with-docs](skills/grill-with-docs/SKILL.md) | Challenge an idea using documentation and external evidence |
| [improve-codebase-architecture](skills/improve-codebase-architecture/SKILL.md) | Identify structural improvements and produce a scoped plan |
| [brainstorming](skills/brainstorming/SKILL.md) | Explore intent, requirements, and design before implementation |
| [code-research](skills/code-research/SKILL.md) | Tiered tool strategy for investigating codebases, libraries, and APIs |
| [dispatching-parallel-agents](skills/dispatching-parallel-agents/SKILL.md) | Run 2+ independent tasks in parallel without shared state |
| [finishing-a-development-branch](skills/finishing-a-development-branch/SKILL.md) | Structured options for merge, PR, or cleanup when work is done |
| [find-skills](skills/find-skills/SKILL.md) | Discover and install agent skills for new capabilities |
| [parallel-debugging](skills/parallel-debugging/SKILL.md) | Debug with competing hypotheses and parallel investigation |
| [refactor](skills/refactor/SKILL.md) | Surgical refactoring to improve maintainability without changing behavior |
| [self-learning](skills/self-learning/SKILL.md) | Learn new technologies from the web and generate reusable skills |
| [subagent-driven-development](skills/subagent-driven-development/SKILL.md) | Execute implementation plans with independent tasks via subagents |
| [task-coordination-strategies](skills/task-coordination-strategies/SKILL.md) | Decompose tasks, design dependency graphs, coordinate multi-agent work |
| [technical-writing](skills/technical-writing/SKILL.md) | Clear, source-grounded READMEs, developer documentation and project copy |
| [test-driven-development](skills/test-driven-development/SKILL.md) | TDD workflow: write tests before implementation code |

### Development Tools
| Skill | Description |
|-------|-------------|
| [agent-browser](skills/agent-browser/SKILL.md) | Automate browser tasks with the agent-browser CLI |
| [code-search](skills/code-search/SKILL.md) | Choose lexical, semantic, or structural code search |
| [osgrep-semantic-search](skills/osgrep-semantic-search/SKILL.md) | Search code by meaning with osgrep |
| [web-research](skills/web-research/SKILL.md) | Find and verify web evidence with available research tools |
| [x-api](skills/x-api/SKILL.md) | Read and manage X content through the X API |
| [ast-grep](skills/ast-grep/SKILL.md) | Structural code search using AST patterns |
| [browser-use](skills/browser-use/SKILL.md) | Automate browser interactions for testing, forms, and data extraction |
| [chrome-devtools](skills/chrome-devtools/SKILL.md) | Browser automation, performance and network analysis with Puppeteer helpers |
| [cli-developer](skills/cli-developer/SKILL.md) | Build CLI tools with argument parsing, interactive prompts, and completions |
| [gh-cli](skills/gh-cli/SKILL.md) | GitHub CLI reference for repos, issues, PRs, Actions, and more |
| [gemini](skills/gemini/SKILL.md) | Gemini CLI for one-shot Q&A, summaries, and generation |
| [ghidra](skills/ghidra/SKILL.md) | Reverse engineer binaries using Ghidra's headless analyzer |
| [obsidian-cli](skills/obsidian-cli/SKILL.md) | Interact with Obsidian vaults via CLI |
| [obsidian-markdown](skills/obsidian-markdown/SKILL.md) | Create Obsidian-flavored Markdown with wikilinks, callouts, and embeds |
| [research-readwise-obsidian](skills/research-readwise-obsidian/SKILL.md) | Research topics with Readwise CLI and produce Obsidian-ready notes with source-linked evidence |
| [playwright](skills/playwright/SKILL.md) | Browser automation for web testing and interaction |
| [tmux](skills/tmux/SKILL.md) | Remote control tmux sessions for interactive CLIs |
| [using-git-worktrees](skills/using-git-worktrees/SKILL.md) | Isolated git worktrees for feature work |
| [jujutsu-vcs](skills/jujutsu-vcs/SKILL.md) | Jujutsu (jj) workflows, isolated agent workspaces and Git compatibility |
| [uv-package-manager](skills/uv-package-manager/SKILL.md) | Fast Python dependency management with uv |

### Python
| Skill | Description |
|-------|-------------|
| [async-python-patterns](skills/async-python-patterns/SKILL.md) | asyncio, concurrent programming, and async/await patterns |
| [python-anti-patterns](skills/python-anti-patterns/SKILL.md) | Common anti-patterns to avoid in Python |
| [python-background-jobs](skills/python-background-jobs/SKILL.md) | Task queues, workers, and event-driven architecture |
| [python-code-style](skills/python-code-style/SKILL.md) | Style, linting, formatting, naming, and documentation standards |
| [python-configuration](skills/python-configuration/SKILL.md) | Config management via environment variables and typed settings |
| [python-design-patterns](skills/python-design-patterns/SKILL.md) | KISS, SoC, SRP, and composition over inheritance |
| [python-error-handling](skills/python-error-handling/SKILL.md) | Validation, exception hierarchies, and partial failure handling |
| [python-observability](skills/python-observability/SKILL.md) | Structured logging, metrics, and distributed tracing |
| [python-performance-optimization](skills/python-performance-optimization/SKILL.md) | Profiling and optimizing with cProfile and memory profilers |
| [python-resilience](skills/python-resilience/SKILL.md) | Retries, exponential backoff, timeouts, and fault tolerance |
| [python-resource-management](skills/python-resource-management/SKILL.md) | Context managers, cleanup patterns, and streaming |
| [python-testing-patterns](skills/python-testing-patterns/SKILL.md) | pytest, fixtures, mocking, and test-driven development |
| [python-type-safety](skills/python-type-safety/SKILL.md) | Type hints, generics, protocols, and strict type checking |

### Architecture & Patterns
| Skill | Description |
|-------|-------------|
| [architecture-decision-records](skills/architecture-decision-records/SKILL.md) | Write and maintain ADRs for technical decision documentation |
| [cqrs-implementation](skills/cqrs-implementation/SKILL.md) | Command Query Responsibility Segregation for scalable systems |
| [error-handling-patterns](skills/error-handling-patterns/SKILL.md) | Cross-language error handling: exceptions, Result types, graceful degradation |
| [memory-safety-patterns](skills/memory-safety-patterns/SKILL.md) | RAII, ownership, smart pointers across Rust, C++, and C |
| [microservices-patterns](skills/microservices-patterns/SKILL.md) | Service boundaries, event-driven communication, and resilience |
| [prompt-engineering-patterns](skills/prompt-engineering-patterns/SKILL.md) | Advanced prompt techniques for production LLM applications |

### Backend & Databases
| Skill | Description |
|-------|-------------|
| [golang-backend-development](skills/golang-backend-development/SKILL.md) | Go backend development: concurrency, web servers, databases, deployment |
| [go-concurrency-patterns](skills/go-concurrency-patterns/SKILL.md) | Goroutines, channels, sync primitives, and context |
| [postgresql-table-design](skills/postgresql-table-design/SKILL.md) | PostgreSQL schema design, indexing, constraints, and performance |
| [spring-boot-engineer](skills/spring-boot-engineer/SKILL.md) | Spring Boot 3.x, Spring Security 6, WebFlux, Spring Cloud |
| [sql-optimization-patterns](skills/sql-optimization-patterns/SKILL.md) | Query optimization, indexing strategies, and EXPLAIN analysis |

### AI/ML & LLM
| Skill | Description |
|-------|-------------|
| [langchain-architecture](skills/langchain-architecture/SKILL.md) | LangChain 1.x and LangGraph for agents, memory, and tool integration |
| [langgraph-docs](skills/langgraph-docs/SKILL.md) | Fetch relevant LangGraph documentation for accurate guidance |
| [llm-evaluation](skills/llm-evaluation/SKILL.md) | Evaluation strategies: automated metrics, human feedback, benchmarking |
| [openai-docs](skills/openai-docs/SKILL.md) | Up-to-date OpenAI API documentation and usage guidance |

### Systems & Security
| Skill | Description |
|-------|-------------|
| [doppler-secrets](skills/doppler-secrets/SKILL.md) | Manage secrets with the Doppler CLI |
| [bash-defensive-patterns](skills/bash-defensive-patterns/SKILL.md) | Defensive Bash for production scripts and CI/CD pipelines |
| [binary-analysis-patterns](skills/binary-analysis-patterns/SKILL.md) | Disassembly, decompilation, control flow, and code pattern recognition |
| [turnstile-spin](skills/turnstile-spin/SKILL.md) | Add Cloudflare Turnstile with guarded creation, recovery and server-side verification |

### Frontend & Design
| Skill | Description |
|-------|-------------|
| [e2e-testing-patterns](skills/e2e-testing-patterns/SKILL.md) | E2E testing with Playwright and Cypress |
| [frontend-design](skills/frontend-design/SKILL.md) | Production-grade frontend interfaces with high design quality |

### Meta
| Skill | Description |
|-------|-------------|
| [create-agent-skills](skills/create-agent-skills/SKILL.md) | Guidance for creating, writing, and refining agent skills |

## Agents

Ask Claude to use an agent by its scoped name, such as `10x-swe:code-reviewer`.
Agents are delegated specialists, rather than slash commands.

| Agent | Use it for |
|---|---|
| [code-reviewer](agents/code-reviewer.md) | Review a specific change against project standards |
| [code-improvement-scanner](agents/code-improvement-scanner.md) | Find code quality and maintainability opportunities |
| [code-simplifier](agents/code-simplifier.md) | Simplify recently changed code while preserving behavior |
| [comment-analyzer](agents/comment-analyzer.md) | Check comment accuracy and usefulness |
| [pr-test-analyzer](agents/pr-test-analyzer.md) | Inspect test coverage and important gaps |
| [silent-failure-hunter](agents/silent-failure-hunter.md) | Find swallowed errors and misleading fallbacks |
| [type-design-analyzer](agents/type-design-analyzer.md) | Evaluate type invariants and encapsulation |
| [ruthless-code-reviewer](agents/ruthless-code-reviewer.md) | Explicitly opt into the confrontational review persona; read its instructions first |

## Commands

These prompt entrypoints appear under `/10x-swe:` in Claude Code. Inspect the linked
instructions and argument hints before use. The command picker shows the available
name for your Claude Code version.

| File | Purpose |
|---|---|
| [create-agent-skill](commands/create-agent-skill.md) | Create or edit a skill with the authoring guide |
| [create-prompt](commands/create-prompt.md) | Prepare a task prompt for another context |
| [research](commands/research.md) | Start a code research task |
| [research-readwise-obsidian](commands/research-readwise-obsidian.md) | Research with Readwise and prepare Obsidian notes |
| [run_prompt](commands/run_prompt.md) | Run selected saved prompts in fresh contexts |

## Maintaining the catalog

When adding or renaming an entrypoint, update its link here. The root test suite
checks skill, agent and command frontmatter, duplicate names within each component
type, and catalog coverage:

```sh
python3 -m unittest discover -s tests -p 'test_plugin_metadata.py' -v
```

Run this from the repository root with PyYAML installed, or use the Python runtime
created by `knowledge setup`.

## Acknowledgments

This plugin builds on the work of:

- [Armin Ronacher](https://github.com/mitsuhiko) — [agent-stuff/skills](https://github.com/mitsuhiko/agent-stuff/tree/main/skills)
- [Peter Steinberger](https://github.com/steipete) — [openclaw/skills](https://github.com/openclaw/openclaw/tree/main/skills)
- [Will Hobson](https://github.com/wshobson) — [agents](https://github.com/wshobson/agents)

## License

MIT

## Portable knowledge integration

Use the root source bootstrap for independent discovery, evidence and bookmark
CLIs. Discover relevant skills and workflows with `skill-search`; load the
selected entrypoints for their instructions.

MCP configuration is opt-in at `examples/mcp.optional.json`. Inspect endpoints and
pin package versions before activating it. Skill authoring uses explicit SKILL_DIR,
SKILL_ROOT and optional COMMAND_ROOT paths, with bundled initialization and basic
validation helpers. Optional specialist references load only when the task needs them.
