<objective>
Evaluate the current technology stack and recommend optimal alternatives for rewriting the software from first principles. Focus on problem-domain fit, efficiency, simplicity, and removing unnecessary complexity.
</objective>

<required_reading>
Before starting, read:
- references/first-principles-analysis.md
- references/bloat-detection-patterns.md
</required_reading>

<inputs>
Required:
- **Current analysis** - Results from repository/binary analysis (architecture, patterns, bloat, requirements)
- **Problem domain** - What does this software actually do? What problem does it solve?

Optional:
- **Constraints** - Team expertise, existing infrastructure, migration timeline, budget
- **Non-functional requirements** - Performance, scalability, reliability, maintainability
- **Priorities** - What matters most? (Speed, simplicity, scalability, cost, developer velocity)
</inputs>

<process>
<phase name="1" label="Problem Domain Analysis">
**Goal:** Understand the core problem being solved, stripped of implementation details

1. **Extract essential requirements**
   From repository analysis:
   ```bash
   # What does the software actually DO?
   # Read: README, docs, user-facing code

   # What are the core operations?
   # - CRUD operations?
   # - Data transformation/processing?
   # - Real-time event handling?
   # - Batch processing?
   # - API serving?
   # - UI rendering?
   ```

2. **Classify the problem domain**
   - **Web application** - Request/response, dynamic content
   - **API service** - RESTful/GraphQL/gRPC endpoint serving
   - **Data processing** - ETL, batch jobs, stream processing
   - **Real-time system** - WebSockets, event streams, low-latency
   - **CLI tool** - Command-line utility, automation scripts
   - **Desktop application** - Native GUI application
   - **Mobile application** - iOS/Android apps
   - **Embedded system** - Firmware, IoT devices
   - **System utility** - Daemon, background service, infrastructure tool

3. **Identify scale requirements**
   ```bash
   # Current scale indicators from analysis
   - Requests per second?
   - Data volume?
   - Concurrent users?
   - Geographic distribution?

   # Future scale needs
   - 10x growth expected?
   - Global distribution required?
   - Real-time latency SLAs?
   ```

4. **Define success criteria for rewrite**
   What would make the rewrite objectively better?
   - 50% reduction in response time?
   - 80% reduction in infrastructure cost?
   - 10x easier to maintain?
   - 5x faster feature development?
   - Zero downtime deployments?

**Output:** Problem statement (domain, scale, requirements, success criteria)
</phase>

<phase name="2" label="Current Stack Evaluation">
**Goal:** Assess current technology choices against the problem domain

1. **Current stack inventory**
   From repository analysis:
   ```
   - Language(s):
   - Framework(s):
   - Database(s):
   - Infrastructure:
   - Build/deploy tools:
   - Key dependencies:
   ```

2. **Fit analysis - is each choice appropriate?**
   For each technology, ask:
   - **Problem fit:** Does this technology align with the problem domain?
     - Using Node.js for CPU-heavy processing? ❌
     - Using microservices for 3-person team? ❌
     - Using MongoDB for transactional data? ❌
     - Using Rails for real-time WebSocket app? ❌

   - **Complexity vs. requirements:**
     - Does the problem need the complexity this tech brings?
     - Kubernetes for simple web app? Likely over-kill
     - React for static content? Probably excessive
     - Microservices for monolithic workload? Unnecessary complexity

   - **Performance characteristics:**
     - Interpreted vs. compiled for hot paths?
     - GC pauses affecting latency SLAs?
     - Framework overhead too high for workload?

3. **Identify mismatches**
   ```
   Technology: <name>
   Problem: <what mismatch>
   Impact: <performance/complexity/cost penalty>
   Evidence: <from analysis - metrics, bloat, complexity>
   ```

**Output:** Current stack assessment (fit, mismatches, impact)
</phase>

<phase name="3" label="First Principles Reconstruction">
**Goal:** Design ideal stack from scratch, ignoring current implementation

1. **Start with minimal requirements**
   "If building this today from scratch, what's the SIMPLEST stack that works?"

   Example thought process:
   ```
   Problem: Serve API endpoints with database reads

   Minimal stack:
   - Language: [choose]
   - Framework: Maybe none? Just HTTP library?
   - Database: [choose based on data model]
   - Deploy: Single binary on VM? Serverless?

   NOT needed yet:
   - Message queue (unless async required)
   - Cache layer (until scale demands it)
   - Service mesh (not at this scale)
   - Complex CI/CD (keep it simple)
   ```

2. **Progressive complexity - add only what's justified**
   For each additional piece of complexity, require justification:

   - **"Do we need a framework?"**
     - NO if: Simple request routing, few endpoints
     - YES if: Complex auth, middleware chain, ORM needs, lots of endpoints

   - **"Do we need a cache?"**
     - NO if: Database fast enough, low traffic
     - YES if: High read volume, expensive queries, latency SLAs

   - **"Do we need microservices?"**
     - NO if: Small team, shared domain, deployment coupling acceptable
     - YES if: Independent scaling needs, team boundaries, polyglot requirements

   - **"Do we need Kubernetes?"**
     - NO if: Handful of services, predictable scaling
     - YES if: Complex orchestration, auto-scaling, multi-region, large scale

3. **Language selection from first principles**
   Match language to problem characteristics:

   | Problem Type | Language Considerations |
   |--------------|-------------------------|
   | **CPU-bound processing** | Compiled languages (Rust, Go, C++, Java) |
   | **I/O-bound API serving** | Any with async (Go, Rust, Node, Python+async) |
   | **Systems programming** | Rust, C, C++, Zig |
   | **Data science/ML** | Python, Julia, R |
   | **Web frontend** | TypeScript, JavaScript |
   | **CLI tools** | Go, Rust, Python (compiled) |
   | **Real-time/embedded** | Rust, C, C++ |
   | **Rapid prototyping** | Python, Ruby, JavaScript |
   | **High-throughput data** | Java, Go, Rust, C++ |

4. **Database selection from first principles**
   Match database to data patterns:

   | Data Pattern | Database Type |
   |--------------|---------------|
   | **ACID transactions, relational** | PostgreSQL, MySQL |
   | **Document store, flexible schema** | MongoDB, DynamoDB |
   | **Key-value cache** | Redis, Memcached |
   | **Time-series data** | InfluxDB, TimescaleDB |
   | **Graph relationships** | Neo4j, DGraph |
   | **Search/full-text** | Elasticsearch, Typesense |
   | **Embedded/local** | SQLite, RocksDB |
   | **Event sourcing** | EventStoreDB, Kafka |

**Output:** First principles stack (minimal viable stack + justified additions)
</phase>

<phase name="4" label="Alternative Stack Evaluation">
**Goal:** Evaluate specific technology alternatives against criteria

1. **Generate alternative stacks**
   For the problem domain, propose 2-3 alternative stacks:

   **Alternative A: Lightweight & Fast**
   ```
   Language: Go / Rust
   Framework: Minimal (stdlib + routing)
   Database: PostgreSQL
   Deploy: Single binary, Docker container
   Rationale: Maximum performance, minimal dependencies, easy deployment
   ```

   **Alternative B: Developer Velocity**
   ```
   Language: Python / Ruby / TypeScript
   Framework: Django / Rails / Next.js
   Database: PostgreSQL
   Deploy: Platform-as-a-Service
   Rationale: Rapid development, rich ecosystem, quick iteration
   ```

   **Alternative C: Cloud-Native**
   ```
   Language: [modern choice]
   Framework: [appropriate]
   Database: Managed cloud DB
   Deploy: Serverless / managed containers
   Rationale: Zero ops, auto-scaling, pay-per-use
   ```

2. **Evaluation matrix**
   Rate each alternative (1-5 scale) on:

   | Criteria | Current | Alt A | Alt B | Alt C |
   |----------|---------|-------|-------|-------|
   | **Performance** | | | | |
   | **Simplicity** | | | | |
   | **Developer velocity** | | | | |
   | **Operational overhead** | | | | |
   | **Scalability** | | | | |
   | **Cost (infra + dev)** | | | | |
   | **Team expertise** | | | | |
   | **Ecosystem maturity** | | | | |
   | **Long-term maintainability** | | | | |

3. **Quantified comparison**
   For each alternative, estimate:
   ```
   - Lines of code: [estimate based on language/framework]
   - Dependencies: [count]
   - Build time: [estimate]
   - Binary size: [estimate]
   - Memory footprint: [estimate]
   - Cold start time: [relevant for serverless]
   - Developer ramp-up: [time for new dev to be productive]
   ```

**Output:** Alternative stacks with evaluation matrix and quantified comparison
</phase>

<phase name="5" label="Migration Complexity Assessment">
**Goal:** Understand the effort required for each alternative

1. **Data migration complexity**
   - Schema changes required?
   - Data transformation needs?
   - Migration downtime?
   - Rollback strategy?

2. **Code rewrite effort**
   ```
   Estimate for each alternative:
   - % of code that can be reused: ___%
   - % that must be rewritten: ___%
   - % that can be auto-migrated: ___%

   Estimated person-months: ___
   ```

3. **Operational migration**
   - Deployment strategy (big bang, blue-green, incremental)
   - Infrastructure changes
   - Monitoring/observability setup
   - Runbook updates

4. **Risk assessment**
   For each alternative:
   ```
   Technical risks:
   -

   Organizational risks:
   -

   Mitigation strategies:
   -
   ```

**Output:** Migration complexity assessment (effort, risks, timeline)
</phase>

<phase name="6" label="Recommendation">
**Goal:** Synthesize analysis into clear recommendation

1. **Primary recommendation**
   ```
   Recommended Stack: [Alternative X]

   Rationale:
   - Best fit for problem domain because [...]
   - Eliminates [X%] of current bloat
   - Reduces operational complexity by [...]
   - Improves performance by [estimated X]
   - Development velocity impact: [positive/neutral/negative]

   Key trade-offs:
   - Pro: [...]
   - Pro: [...]
   - Con: [...]
   - Mitigation for cons: [...]
   ```

2. **Migration strategy**
   ```
   Phase 1: [Foundation - X weeks]
   - Set up infrastructure
   - Core domain logic migration
   - Database migration

   Phase 2: [Feature parity - X weeks]
   - Remaining features
   - API compatibility
   - Testing

   Phase 3: [Transition - X weeks]
   - Blue-green deployment
   - Monitoring
   - Rollback procedures

   Total timeline: [X months]
   Risk level: [Low/Medium/High]
   ```

3. **Success metrics**
   ```
   Track these metrics to validate rewrite success:
   - Performance: [latency, throughput]
   - Efficiency: [CPU, memory, cost]
   - Complexity: [LOC, dependencies, deployment steps]
   - Reliability: [uptime, error rate]
   - Velocity: [time to implement new features]
   ```

4. **Alternative paths**
   ```
   If constraints change:
   - If priority shifts to [X], consider [Alternative Y]
   - If timeline is critical, consider [incremental approach]
   - If team lacks expertise, consider [different choice]
   ```

**Output:** Comprehensive recommendation with migration strategy
</phase>

<phase name="7" label="Generate Recommendation Report">
**Goal:** Create actionable rewrite recommendation document

Use template: `templates/rewrite-recommendation.md`

Include:
1. **Executive Summary** - One-paragraph recommendation
2. **Problem Analysis** - Core problem, current stack issues
3. **First Principles Stack** - Ideal minimal stack
4. **Alternative Evaluation** - Comparison matrix
5. **Primary Recommendation** - Chosen stack with rationale
6. **Migration Strategy** - Phased approach with timeline
7. **Success Metrics** - How to measure rewrite success
8. **Risk Assessment** - Risks and mitigation strategies
9. **Appendices** - Detailed analysis, code samples, architecture diagrams

Save report:
```bash
Write: analysis-reports/<project-name>-rewrite-recommendation-<date>.md
```
</phase>
</process>

<evaluation_frameworks>
**Problem-Domain Fit Framework:**
```
For technology choice X solving problem Y:

1. Does X's strengths align with Y's requirements?
   - Performance characteristics match?
   - Concurrency model appropriate?
   - I/O patterns compatible?

2. Does X's complexity match Y's complexity?
   - Not over-engineered?
   - Not under-powered?

3. Does X's ecosystem support Y's needs?
   - Libraries available?
   - Tooling mature?
   - Community active?

4. Does X fit the team and organization?
   - Expertise available?
   - Hiring feasible?
   - Long-term support?
```

**Simplicity Framework:**
```
Prefer:
- Fewer moving parts over more
- Direct solutions over abstracted ones
- Standard patterns over custom frameworks
- Boring technology over bleeding edge
- Explicit over magical/convention-based
- Composition over inheritance
- Data over code when possible

Add complexity only when:
- Scale demands it (proven, not anticipated)
- Requirements mandate it (not just nice-to-have)
- Simpler approach tried and failed
```

**Modern Tech Stack Archetypes (2026):**
```
**High-Performance Backend:**
- Rust + Axum + PostgreSQL
- Go + stdlib/Gin + PostgreSQL
- Java + Spring Boot (Virtual Threads) + PostgreSQL

**Developer Velocity Web:**
- Next.js + TypeScript + PostgreSQL + Vercel
- SvelteKit + TypeScript + PostgreSQL
- Remix + TypeScript + PostgreSQL

**CLI/Systems:**
- Rust + Clap
- Go + Cobra
- Zig

**Data-Intensive:**
- Python + Polars + DuckDB
- Rust + DataFusion
- Go + ClickHouse

**Serverless:**
- TypeScript + AWS Lambda + DynamoDB
- Python + GCP Cloud Functions + Firestore
- Rust + Lambda (for performance-critical)

**Real-Time:**
- Elixir + Phoenix LiveView
- Go + WebSockets
- Rust + Axum + WebSockets
```
</evaluation_frameworks>

<success_criteria>
Recommendation is complete when:
- Problem domain clearly understood and documented
- Current stack evaluated against problem fit
- First principles stack designed from scratch
- 2-3 alternative stacks proposed and evaluated
- Migration complexity assessed with timeline
- Primary recommendation made with clear rationale
- Success metrics defined
- Report generated with actionable next steps
- All recommendations backed by analysis evidence
</success_criteria>
