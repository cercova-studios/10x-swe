# 10x-swe

 A terminal-first AI agent plugin with 69 skills for software engineering, debugging, architecture, and development workflows.

## Skills

### Workflow & Process
| Skill | Description |
|-------|-------------|
| brainstorming | Explore intent, requirements, and design before implementation |
| code-research | Tiered tool strategy for investigating codebases, libraries, and APIs |
| dispatching-parallel-agents | Run 2+ independent tasks in parallel without shared state |
| finishing-a-development-branch | Structured options for merge, PR, or cleanup when work is done |
| find-skills | Discover and install agent skills for new capabilities |
| parallel-debugging | Debug with competing hypotheses and parallel investigation |
| refactor | Surgical refactoring to improve maintainability without changing behavior |
| self-learning | Learn new technologies from the web and generate reusable skills |
| subagent-driven-development | Execute implementation plans with independent tasks via subagents |
| task-coordination-strategies | Decompose tasks, design dependency graphs, coordinate multi-agent work |
| test-driven-development | TDD workflow: write tests before implementation code |

### Development Tools
| Skill | Description |
|-------|-------------|
| ast-grep | Structural code search using AST patterns |
| browser-use | Automate browser interactions for testing, forms, and data extraction |
| chrome-devtools | Debug web pages, analyze performance, inspect network via Chrome DevTools MCP |
| cli-developer | Build CLI tools with argument parsing, interactive prompts, and completions |
| gh-cli | GitHub CLI reference for repos, issues, PRs, Actions, and more |
| gemini | Gemini CLI for one-shot Q&A, summaries, and generation |
| ghidra | Reverse engineer binaries using Ghidra's headless analyzer |
| obsidian-cli | Interact with Obsidian vaults via CLI |
| obsidian-markdown | Create Obsidian-flavored Markdown with wikilinks, callouts, and embeds |
| research-readwise-obsidian | Research topics with Readwise CLI and produce Obsidian-ready notes with source-linked evidence |
| playwright | Browser automation for web testing and interaction |
| tmux | Remote control tmux sessions for interactive CLIs |
| using-git-worktrees | Isolated git worktrees for feature work |
| use-jujutsu-vcs | Jujutsu (jj) version control workflows and Git compatibility |
| uv-package-manager | Fast Python dependency management with uv |

### Python
| Skill | Description |
|-------|-------------|
| async-python-patterns | asyncio, concurrent programming, and async/await patterns |
| python-anti-patterns | Common anti-patterns to avoid in Python |
| python-background-jobs | Task queues, workers, and event-driven architecture |
| python-code-style | Style, linting, formatting, naming, and documentation standards |
| python-configuration | Config management via environment variables and typed settings |
| python-design-patterns | KISS, SoC, SRP, and composition over inheritance |
| python-error-handling | Validation, exception hierarchies, and partial failure handling |
| python-observability | Structured logging, metrics, and distributed tracing |
| python-performance-optimization | Profiling and optimizing with cProfile and memory profilers |
| python-resilience | Retries, exponential backoff, timeouts, and fault tolerance |
| python-resource-management | Context managers, cleanup patterns, and streaming |
| python-testing-patterns | pytest, fixtures, mocking, and test-driven development |
| python-type-safety | Type hints, generics, protocols, and strict type checking |

### Architecture & Patterns
| Skill | Description |
|-------|-------------|
| architecture-decision-records | Write and maintain ADRs for technical decision documentation |
| cqrs-implementation | Command Query Responsibility Segregation for scalable systems |
| error-handling-patterns | Cross-language error handling: exceptions, Result types, graceful degradation |
| memory-safety-patterns | RAII, ownership, smart pointers across Rust, C++, and C |
| microservices-patterns | Service boundaries, event-driven communication, and resilience |
| prompt-engineering-patterns | Advanced prompt techniques for production LLM applications |

### Backend & Databases
| Skill | Description |
|-------|-------------|
| golang-backend-development | Go backend development: concurrency, web servers, databases, deployment |
| go-concurrency-patterns | Goroutines, channels, sync primitives, and context |
| postgresql-table-design | PostgreSQL schema design, indexing, constraints, and performance |
| spring-boot-engineer | Spring Boot 3.x, Spring Security 6, WebFlux, Spring Cloud |
| sql-optimization-patterns | Query optimization, indexing strategies, and EXPLAIN analysis |

### AI/ML & LLM
| Skill | Description |
|-------|-------------|
| langchain-architecture | LangChain 1.x and LangGraph for agents, memory, and tool integration |
| langgraph-docs | Fetch relevant LangGraph documentation for accurate guidance |
| llm-evaluation | Evaluation strategies: automated metrics, human feedback, benchmarking |
| openai-docs | Up-to-date OpenAI API documentation and usage guidance |

### Systems & Security
| Skill | Description |
|-------|-------------|
| bash-defensive-patterns | Defensive Bash for production scripts and CI/CD pipelines |
| binary-analysis-patterns | Disassembly, decompilation, control flow, and code pattern recognition |

### Frontend & Design
| Skill | Description |
|-------|-------------|
| e2e-testing-patterns | E2E testing with Playwright and Cypress |
| frontend-design | Production-grade frontend interfaces with high design quality |

### Meta
| Skill | Description |
|-------|-------------|
| create-agent-skills | Guidance for creating, writing, and refining agent skills |

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
pin package versions before activating it; the plugin no longer launches MCP
servers or changes directory environment state by default. Skill authoring uses explicit SKILL_DIR, SKILL_ROOT and optional COMMAND_ROOT paths;
no per-working-directory state or compatibility links are created.
