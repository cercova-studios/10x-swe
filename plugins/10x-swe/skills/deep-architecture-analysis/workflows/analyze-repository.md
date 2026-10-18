<objective>
Perform comprehensive architecture analysis of a GitHub repository to understand its structure, identify inefficiencies, detect bloat, find security issues, and deconstruct from first principles.
</objective>

<required_reading>
Before starting, read:
- references/bloat-detection-patterns.md
- references/first-principles-analysis.md
</required_reading>

<inputs>
Required:
- **Repository URL or path** - GitHub URL (e.g., https://github.com/owner/repo) or local path

Optional:
- **Focus areas** - Specific aspects to emphasize (performance, security, architecture, bloat)
- **Context** - Why analyzing? (rewrite planning, migration, audit)
</inputs>

<process>
<phase name="1" label="Repository Discovery">
**Goal:** Get broad overview of the project

1. **Clone or locate repository**
   ```bash
   # If GitHub URL provided, clone it
   git clone <url> /tmp/analysis-<repo-name>
   cd /tmp/analysis-<repo-name>

   # Or use existing local path
   cd <local-path>
   ```

2. **Gather metadata**
   ```bash
   # Repository stats
   git log --oneline --all | wc -l  # commit count
   git ls-files | wc -l             # file count
   du -sh .                          # size
   git shortlog -sn --all           # contributor activity

   # Recent activity
   git log --oneline --all -20
   ```

3. **Identify language and framework**
   ```bash
   # Language breakdown
   tokei  # or: cloc .

   # Framework detection
   ls -la | grep -E "package.json|requirements.txt|go.mod|Cargo.toml|pom.xml|build.gradle"
   ```

4. **Use MCP Deepwiki if available**
   ```
   mcp__deepwiki__read_wiki_structure: "owner/repo"
   mcp__deepwiki__ask_question: "What is the overall architecture and purpose?"
   ```

**Output:** Repository summary (size, languages, frameworks, age, activity)
</phase>

<phase name="2" label="Architecture Mapping">
**Goal:** Understand the high-level structure and component relationships

1. **Directory structure analysis**
   ```bash
   # Project layout
   tree -L 3 -d  # or: find . -type d -maxdepth 3

   # Key directories
   Glob: "**/src/**" "**/lib/**" "**/internal/**" "**/pkg/**"
   ```

2. **Entry points identification**
   ```bash
   # Find main entry points
   Grep: "func main|def main|public static void main|if __name__"

   # API endpoints
   Grep: "@app.route|@router|@Controller|app.get|app.post"

   # CLI commands
   Grep: "cobra.Command|click.command|Commander"
   ```

3. **Dependency analysis**
   ```bash
   # Package dependencies
   cat package.json | jq '.dependencies, .devDependencies'
   # or: cat requirements.txt
   # or: cat go.mod
   # or: cat Cargo.toml

   # Count dependencies
   # Identify heavy/bloated dependencies
   npm list --depth=0  # or equivalent for language
   ```

4. **Component boundaries**
   ```bash
   # Find interfaces and boundaries
   Grep: "interface|abstract class|trait|protocol"

   # Service/module definitions
   Grep: "class.*Service|module.*|package "
   ```

**Output:** Architecture diagram (components, layers, boundaries, data flows)
</phase>

<phase name="3" label="Code Pattern Analysis">
**Goal:** Identify common patterns, anti-patterns, and code quality issues

1. **Design patterns detection**
   ```bash
   # Common patterns
   Grep: "Factory|Singleton|Observer|Strategy|Builder|Adapter"

   # Read key files
   Read: <identified-pattern-files>
   ```

2. **Anti-pattern detection**
   ```bash
   # God objects (large classes)
   fd -e py -e js -e ts -e go | xargs wc -l | sort -n | tail -20

   # Circular dependencies
   # Use madge (JS), pydeps (Python), or go mod graph

   # Deep nesting
   Grep: "        if|        for|        while" -A 2
   ```

3. **Code complexity**
   ```bash
   # Cyclomatic complexity (use language-specific tools)
   radon cc . -a  # Python
   # or: lizard
   # or: gocyclo
   ```

4. **Dead code detection**
   ```bash
   # Unused exports/functions
   # Use language-specific tools: eslint, pylint, golangci-lint

   # Commented code
   Grep: "//.*TODO|//.*FIXME|//.*HACK|#.*TODO"
   ```

**Output:** Pattern analysis (good patterns, anti-patterns, complexity hotspots)
</phase>

<phase name="4" label="Efficiency & Bloat Analysis">
**Goal:** Identify computational waste, bloat, and over-engineering

1. **Dependency bloat**
   ```bash
   # Large dependencies
   npm list --depth=0 --parseable | xargs du -sh | sort -h

   # Transitive dependency explosion
   npm ls --all | wc -l

   # Unused dependencies
   depcheck  # or: pip-autoremove --list
   ```

2. **Code bloat**
   ```bash
   # Large files
   fd -t f | xargs wc -l | sort -n | tail -30

   # Duplicate code
   jscpd . --min-lines 5  # or use language-specific tools

   # Over-abstraction
   Grep: "Abstract.*Factory|Manager|Handler|Wrapper|Adapter" -i
   ```

3. **Algorithmic inefficiency**
   ```bash
   # Nested loops
   Grep: "for.*for|for.*while|while.*for"

   # N+1 queries
   Grep: "for.*query|for.*find|for.*select"

   # Inefficient data structures
   Grep: ".*\\.filter\\(.*\\.filter\\(|.*\\.map\\(.*\\.map\\("
   ```

4. **Build bloat**
   ```bash
   # Build size
   ls -lh dist/ build/ target/

   # Bundle analysis
   # webpack-bundle-analyzer or equivalent
   ```

**Output:** Bloat report (dependencies, code, build size, algorithmic inefficiency)
</phase>

<phase name="5" label="Security Surface Assessment">
**Goal:** Identify potential vulnerabilities, attack surfaces, and security issues

1. **Input validation analysis**
   ```bash
   # User input handling
   Grep: "request\\.|req\\.|input|user.*input|query\\.|params\\."

   # Validation presence
   Grep: "validate|sanitize|escape|whitelist"
   ```

2. **Authentication & authorization**
   ```bash
   # Auth flows
   Grep: "authenticate|login|session|token|jwt|oauth"

   # Authorization checks
   Grep: "authorize|permission|role|isAdmin|canAccess"
   ```

3. **Data exposure**
   ```bash
   # Secrets in code
   Grep: "password|secret|api.*key|token.*=" -i

   # Logging sensitive data
   Grep: "log.*password|console.*secret|print.*token"
   ```

4. **Injection vulnerabilities**
   ```bash
   # SQL injection
   Grep: "execute.*\\+|query.*\\+|SELECT.*\\+|raw.*sql"

   # Command injection
   Grep: "exec|system|shell|subprocess|eval"

   # XSS
   Grep: "innerHTML|dangerouslySetInnerHTML|v-html"
   ```

5. **Dependency vulnerabilities**
   ```bash
   # Security audit
   npm audit  # or: pip-audit, cargo audit, go list -m
   ```

**Output:** Security report (attack surfaces, vulnerabilities, hardening recommendations)
</phase>

<phase name="6" label="First Principles Deconstruction">
**Goal:** Question every layer of complexity and identify what's truly necessary

1. **Ask fundamental questions:**
   - What problem is this software actually solving?
   - What's the minimal viable architecture for this problem?
   - Which abstractions are load-bearing vs. incidental complexity?
   - Which dependencies are essential vs. convenience?
   - Where did complexity creep in unnecessarily?

2. **Trace feature complexity:**
   ```bash
   # For each major feature, map the path from user action to result
   # Count layers of abstraction
   # Identify where indirection adds no value
   ```

3. **Evaluate each layer:**
   - **Framework choice** - Is this framework solving a real problem or adding ceremony?
   - **Architecture patterns** - Is microservices/serverless/etc. justified by scale?
   - **OOP hierarchies** - Are these class hierarchies solving polymorphism needs or just structure?
   - **Middleware layers** - Is each middleware adding value or just passing through?

4. **Reconstruct from scratch mentally:**
   - If starting today with current requirements, what would you build?
   - What's the delta between current state and ideal state?
   - Which complexity is essential vs. historical accident?

**Output:** First principles analysis (necessary vs. incidental complexity, simplification opportunities)
</phase>

<phase name="7" label="Synthesize Findings">
**Goal:** Create comprehensive analysis report

Use template: `templates/architecture-analysis-report.md`

Include:
1. **Executive Summary** - Key findings in 3-5 bullet points
2. **Architecture Overview** - Component diagram and description
3. **Efficiency Analysis** - Bloat, waste, over-engineering identified
4. **Security Assessment** - Attack surfaces and vulnerabilities
5. **First Principles Deconstruction** - What complexity is unnecessary
6. **Quantified Impact** - Lines of code, dependencies, build size, complexity metrics
7. **Recommendations** - Prioritized improvements for rewrite/refactor

Save report:
```bash
Write: analysis-reports/<repo-name>-architecture-analysis-<date>.md
```
</phase>
</process>

<tools>
**Essential tools:**
- `Grep`, `Glob`, `Read` - Code exploration
- `Bash` - Git analysis, dependency tools, static analysis
- `Task(subagent_type=Explore)` - Open-ended codebase exploration
- MCP Deepwiki - Repository documentation
- MCP Exa - Semantic code search

**Language-specific tools (via Bash):**
- **JavaScript/TypeScript:** `madge`, `depcheck`, `webpack-bundle-analyzer`, `eslint`
- **Python:** `radon`, `pydeps`, `pip-audit`, `pylint`, `bandit`
- **Go:** `go mod graph`, `gocyclo`, `golangci-lint`, `staticcheck`
- **Rust:** `cargo tree`, `cargo-bloat`, `cargo-audit`, `clippy`
- **General:** `tokei`, `cloc`, `lizard`, `jscpd`, `semgrep`, `codeql`
</tools>

<output_format>
Create structured markdown report using template:
`templates/architecture-analysis-report.md`

Include:
- Visual diagrams (ASCII art or Mermaid)
- Quantified metrics (LOC, dependencies, complexity scores)
- Code examples for each finding
- Prioritized recommendations
- File paths with line numbers for all references
</output_format>

<success_criteria>
Analysis is complete when:
- All 7 phases executed thoroughly
- Architecture fully mapped with component diagram
- Bloat quantified (dependencies, LOC, build size)
- Security surface documented with severity ratings
- First principles analysis questions all complexity
- Report generated with actionable recommendations
- Evidence provided for all findings (code snippets, metrics)
</success_criteria>
