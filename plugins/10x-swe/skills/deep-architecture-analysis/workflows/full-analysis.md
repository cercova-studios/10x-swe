<objective>
Perform comprehensive analysis combining both repository (source code) and binary (compiled artifacts) analysis for complete understanding of the software system.
</objective>

<required_reading>
Before starting, read:
- workflows/analyze-repository.md
- workflows/analyze-binary.md
- references/first-principles-analysis.md
</required_reading>

<inputs>
Required:
- **Repository URL or path** - GitHub URL or local path to source code
- **Binary path(s)** - Path(s) to compiled executable(s)

Optional:
- **Build instructions** - How to build binaries from source (to correlate source with binary)
- **Focus areas** - Specific aspects to emphasize
- **Rewrite intent** - Planning to rewrite? Need tech stack recommendations?
</inputs>

<process>
<phase name="1" label="Repository Analysis">
**Goal:** Understand source code architecture and patterns

Execute complete repository analysis:
→ Follow workflow: `workflows/analyze-repository.md`

Save intermediate results:
```bash
Write: /tmp/repository-analysis-<project>.md
```

**Key outputs to preserve:**
- Architecture diagram
- Dependency tree
- Bloat metrics
- Security findings
- Code patterns
</phase>

<phase name="2" label="Binary Analysis">
**Goal:** Understand compiled artifact characteristics

For each binary artifact:
→ Follow workflow: `workflows/analyze-binary.md`

Save intermediate results:
```bash
Write: /tmp/binary-analysis-<binary-name>.md
```

**Key outputs to preserve:**
- Binary profile
- Runtime behavior
- Performance characteristics
- Security features
- Size breakdown
</phase>

<phase name="3" label="Source-to-Binary Correlation">
**Goal:** Understand how source code translates to binary characteristics

1. **Build artifacts correlation**
   ```bash
   # If build possible, build from source
   # Then compare:

   # Binary size vs LOC
   echo "Lines of code: $(find src -type f | xargs wc -l | tail -1)"
   echo "Binary size: $(ls -lh <binary> | awk '{print $5}')"
   echo "Ratio: $(echo "scale=2; <binary-bytes> / <loc>" | bc) bytes/LOC"

   # This ratio reveals compilation efficiency
   # High ratio = bloat (large runtime, dependencies, debug info)
   # Low ratio = efficient (optimized, minimal runtime)
   ```

2. **Dependency verification**
   ```bash
   # Compare source dependencies with binary dependencies

   # Source (from package.json, requirements.txt, etc.)
   Source dependencies: [list]

   # Binary (from ldd, otool -L)
   Binary dependencies: [list]

   # Bloat check: are all binary deps justified by source deps?
   ```

3. **Code pattern manifestation**
   ```
   From repository analysis, identified patterns:
   - [Pattern 1: e.g., Factory pattern]

   In binary:
   - How does this pattern manifest in assembly?
   - Function call overhead?
   - Inlining optimizations applied?

   Example:
   objdump -d <binary> | grep -A 10 "Factory"
   ```

4. **Performance correlation**
   ```
   Algorithmic complexity from source: [e.g., O(n²) loop]
   Binary hot path: [from perf/profiling]

   Do they align?
   - If source has O(n²) and binary shows hot path there: ✓ Expected
   - If source seems clean but binary is slow: optimizer failure or hidden cost
   ```

5. **Security correlation**
   ```
   Source-level security:
   - [Input validation present? Y/N]
   - [SQL parameterization? Y/N]

   Binary-level security:
   - [PIE enabled? Y/N]
   - [Stack canary? Y/N]
   - [Dangerous functions present? Y/N]

   Gaps between source intent and binary reality?
   ```

**Output:** Correlation analysis (source patterns → binary characteristics)
</phase>

<phase name="4" label="Unified Bloat Analysis">
**Goal:** Identify bloat at all levels of the stack

1. **Source bloat** (from repository analysis)
   ```
   - Unused dependencies: [count, size]
   - Dead code: [estimated LOC]
   - Over-abstraction: [examples]
   - Total source bloat impact: [X%]
   ```

2. **Build bloat**
   ```bash
   # Build artifacts size
   du -sh dist/ build/ target/

   # Compare debug vs release
   ls -lh <binary-debug> <binary-release>

   # Strip unused code
   strip <binary>
   ls -lh <binary>  # Size after strip

   # Bloat from build: [X MB, Y%]
   ```

3. **Runtime bloat** (from binary analysis)
   ```
   - Shared library overhead: [size]
   - Runtime/VM overhead: [size if applicable]
   - Unused code in binary: [estimate from symbols]
   - Total runtime bloat: [X%]
   ```

4. **Total bloat calculation**
   ```
   Original size: [X MB]
   Bloat breakdown:
   - Source level: [Y MB] - unused deps, dead code
   - Build level: [Z MB] - debug info, unoptimized
   - Runtime level: [W MB] - framework overhead

   Potential size if minimal: [X - Y - Z - W MB]
   Bloat reduction opportunity: [percentage]
   ```

**Output:** Unified bloat report (all levels, quantified, reduction potential)
</phase>

<phase name="5" label="Unified Security Assessment">
**Goal:** Complete security posture from source to binary

1. **Vulnerability surface matrix**
   ```
   | Layer | Vulnerability | Severity | Evidence |
   |-------|---------------|----------|----------|
   | Source | SQL injection risk | High | Unparameterized query in auth.py:45 |
   | Source | XSS in template | Medium | Unescaped output in view.html:12 |
   | Binary | No PIE | Medium | checksec shows no PIE |
   | Binary | Hardcoded secret | High | String "api_key=..." at offset 0x4a3f |
   | Runtime | Unencrypted network | High | strace shows no TLS syscalls |
   ```

2. **Attack surface map**
   ```
   Entry points (from source):
   - HTTP endpoints: [list]
   - CLI arguments: [list]
   - File inputs: [list]

   System interactions (from binary):
   - Network: [ports, protocols]
   - Filesystem: [paths accessed]
   - IPC: [sockets, pipes]

   Attack surface score: [High/Medium/Low]
   ```

3. **Security recommendations prioritized**
   ```
   1. [Critical] Fix SQL injection in auth module
   2. [Critical] Enable PIE in build flags
   3. [High] Remove hardcoded secrets, use env vars
   4. [High] Enable TLS for all network communication
   5. [Medium] Add input validation for X
   ...
   ```

**Output:** Unified security assessment (source → binary → runtime)
</phase>

<phase name="6" label="Performance Synthesis">
**Goal:** Understand performance from all angles

1. **Theoretical performance** (from source analysis)
   ```
   Algorithmic complexity:
   - Hottest code path: O(?)
   - Database queries: N+1 issues?
   - I/O patterns: blocking vs async?
   ```

2. **Compiled performance** (from binary analysis)
   ```
   Optimization level: [O0/O1/O2/O3]
   Inlining: [evidence from disassembly]
   Vectorization: [SIMD instructions present?]
   ```

3. **Runtime performance** (from dynamic analysis)
   ```
   Actual hot paths: [from perf/profiling]
   Syscall overhead: [from strace -c]
   Memory usage: [from valgrind/heaptrack]
   ```

4. **Performance bottlenecks prioritized**
   ```
   1. [Critical] O(n²) loop in data processor - algorithmic improvement needed
   2. [High] Unoptimized build - enable O3 and LTO
   3. [High] Blocking I/O in async context - rewrite to async
   4. [Medium] Excessive allocations - use object pooling
   ```

**Output:** Performance analysis synthesis (bottlenecks prioritized with evidence)
</phase>

<phase name="7" label="First Principles Deconstruction">
**Goal:** Holistic evaluation of whether this software is efficiently designed

1. **Essential functionality**
   ```
   What does this software ACTUALLY do?
   - Core operations: [list]
   - Essential complexity: [what MUST be complex]
   - Incidental complexity: [what's unnecessarily complex]
   ```

2. **Stack-to-problem fit**
   ```
   Problem: [describe]
   Current stack: [from analysis]

   Is the stack appropriate?
   - Language choice: [appropriate? over/under-powered?]
   - Framework choice: [justified? overkill?]
   - Architecture: [fits scale? over-engineered?]
   ```

3. **Complexity audit**
   ```
   For each layer of abstraction:
   - Is it load-bearing? (Remove it = breaks)
   - Or is it accidental? (Historical, convenience, trend-chasing)

   Example:
   - 5 middleware layers: 2 load-bearing, 3 could be removed
   - 15 microservices: workload doesn't justify split
   - ORM framework: adds complexity, hand-written SQL would be simpler
   ```

4. **Minimal viable architecture**
   ```
   If starting from scratch today:
   - Language: [choice based on problem]
   - Framework: [minimal or none]
   - Architecture: [monolith vs services]
   - Database: [appropriate for data model]
   - Infrastructure: [simple as possible]

   Gap between current and ideal:
   - Current complexity: [score 1-10]
   - Minimal viable: [score 1-10]
   - Reduction opportunity: [X points, Y%]
   ```

**Output:** First principles evaluation (essential vs accidental complexity)
</phase>

<phase name="8" label="Rewrite Recommendation">
**Goal:** Synthesize all findings into rewrite recommendation

If user indicated rewrite intent:
→ Follow workflow: `workflows/recommend-tech-stack.md`

Use all analysis outputs as inputs:
- Repository analysis results
- Binary analysis results
- Correlation findings
- Bloat metrics
- Security assessment
- Performance bottlenecks
- First principles evaluation

**Output:** Comprehensive rewrite recommendation
</phase>

<phase name="9" label="Generate Comprehensive Report">
**Goal:** Create master analysis document

Use template: `templates/architecture-analysis-report.md`

Sections:
1. **Executive Summary**
   - Key findings (top 5 bullets)
   - Primary recommendation
   - Impact potential

2. **Repository Analysis**
   - Include: architecture, patterns, dependencies
   - Link to: /tmp/repository-analysis-<project>.md

3. **Binary Analysis**
   - Include: profiles, runtime, performance
   - Link to: /tmp/binary-analysis-*.md

4. **Correlation Analysis**
   - Source-to-binary mapping
   - Bloat unified view
   - Security complete picture

5. **Performance Synthesis**
   - Bottlenecks across all layers
   - Prioritized with evidence

6. **First Principles Evaluation**
   - Essential vs accidental complexity
   - Minimal viable architecture

7. **Recommendations**
   - Immediate wins (low-hanging fruit)
   - Strategic improvements
   - Rewrite considerations (if applicable)

8. **Appendices**
   - Detailed metrics
   - Code samples
   - Architecture diagrams
   - Tool outputs

Save master report:
```bash
Write: analysis-reports/<project>-full-analysis-<date>.md
```
</phase>
</process>

<correlation_techniques>
**Effective source-to-binary correlation methods:**

1. **Symbol matching**
   ```bash
   # Find source function in binary
   nm <binary> | grep "<function_name>"
   objdump -d <binary> | grep "<function_name>:" -A 20
   ```

2. **Strings correlation**
   ```bash
   # Find source strings in binary
   grep -r "specific error message" src/
   strings <binary> | grep "specific error message"
   ```

3. **Control flow correlation**
   ```
   Source: if (x > 100) { ... }
   Binary: Look for comparison, conditional jump
   objdump -d <binary> | grep -E "cmp.*0x64|test.*test"
   ```

4. **Library correlation**
   ```bash
   # Source imports
   grep -r "import.*library" src/

   # Binary links
   ldd <binary> | grep library
   ```

5. **Build verification**
   ```bash
   # Build from source
   make clean && make

   # Compare checksums
   sha256sum <original-binary>
   sha256sum <built-binary>

   # If different, investigate build flags
   ```
</correlation_techniques>

<success_criteria>
Full analysis is complete when:
- Repository analysis completed (all phases)
- Binary analysis completed (all phases)
- Source-to-binary correlation performed
- Unified bloat analysis quantified
- Complete security assessment across all layers
- Performance synthesis with prioritized bottlenecks
- First principles evaluation completed
- Rewrite recommendation generated (if requested)
- Comprehensive master report created
- All findings backed by evidence from multiple analysis layers
</success_criteria>
