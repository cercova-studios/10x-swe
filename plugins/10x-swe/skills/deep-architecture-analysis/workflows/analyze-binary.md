<objective>
Reverse engineer compiled application binaries across all architectures to understand program structure, identify inefficiencies, detect potential vulnerabilities, and analyze runtime behavior.
</objective>

<required_reading>
Before starting, read:
- references/binary-analysis-tools.md
- references/first-principles-analysis.md
</required_reading>

<inputs>
Required:
- **Binary path** - Path to executable file (ELF, PE, Mach-O, etc.)

Optional:
- **Architecture hint** - Expected architecture if known (x86, x64, ARM, ARM64, RISC-V)
- **Analysis depth** - Surface level, moderate, or deep reverse engineering
- **Focus areas** - Performance, security, memory, system calls
</inputs>

<process>
<phase name="1" label="Binary Identification">
**Goal:** Determine binary format, architecture, and basic properties

1. **File type detection**
   ```bash
   file <binary-path>

   # Detailed info
   readelf -h <binary>     # ELF (Linux)
   otool -hv <binary>      # Mach-O (macOS)
   objdump -f <binary>     # Universal

   # Check if stripped
   file <binary> | grep -q "not stripped" && echo "Has symbols" || echo "Stripped"
   ```

2. **Architecture detection**
   ```bash
   # Determine CPU architecture
   readelf -h <binary> | grep Machine  # ELF
   lipo -info <binary>                 # macOS universal binary

   # Common architectures:
   # x86 (i386, i686)
   # x86_64 (amd64)
   # ARM (armv7, armv8)
   # ARM64 (aarch64)
   # RISC-V (riscv32, riscv64)
   # PowerPC, MIPS, SPARC (legacy)
   ```

3. **Binary metadata**
   ```bash
   # File size and sections
   ls -lh <binary>
   readelf -S <binary> | head -30  # Section headers

   # Build info (if present)
   strings <binary> | grep -E "GCC|clang|rustc|go" | head -5

   # Dependencies
   ldd <binary>                     # Linux
   otool -L <binary>                # macOS
   objdump -p <binary> | grep NEEDED # Universal
   ```

**Output:** Binary profile (format, architecture, size, stripped status, dependencies)
</phase>

<phase name="2" label="Static Analysis">
**Goal:** Analyze binary structure without execution

1. **Symbols and functions**
   ```bash
   # If not stripped
   nm <binary> | grep -E " T | t " | head -50  # Functions
   nm -D <binary>                               # Dynamic symbols

   # Function count
   nm <binary> | grep -E " T " | wc -l

   # If stripped, use alternative methods
   objdump -d <binary> | grep -E "^[0-9a-f]+ <.*>:" | wc -l
   ```

2. **Strings analysis**
   ```bash
   # Extract strings (potential config, URLs, secrets)
   strings <binary> > /tmp/binary-strings.txt

   # Interesting patterns
   grep -E "http://|https://|ftp://" /tmp/binary-strings.txt
   grep -E "password|secret|token|api.*key" /tmp/binary-strings.txt -i
   grep -E "127\\.0\\.0\\.1|localhost|0\\.0\\.0\\.0" /tmp/binary-strings.txt
   grep -E "/tmp/|/var/|/etc/" /tmp/binary-strings.txt
   grep -E "\\.so|\\.dll|\\.dylib" /tmp/binary-strings.txt

   # Error messages and logs
   grep -E "error|failed|exception" /tmp/binary-strings.txt -i | head -20
   ```

3. **Disassembly**
   ```bash
   # Full disassembly
   objdump -d <binary> > /tmp/binary-disasm.txt

   # Entry point
   readelf -h <binary> | grep "Entry point"
   objdump -d <binary> | grep "<_start>:" -A 30

   # Main function (if symbols available)
   objdump -d <binary> | grep "<main>:" -A 50
   ```

4. **Control flow analysis**
   ```bash
   # Use Ghidra, Binary Ninja, or radare2 for advanced CFG
   r2 -A <binary> <<EOF
   aaa
   afl
   pdf @ main
   EOF
   ```

**Output:** Static analysis report (functions, strings, disassembly samples, control flow)
</phase>

<phase name="3" label="Dynamic Analysis">
**Goal:** Observe binary behavior during execution

**WARNING:** Only run if binary is from trusted source or in isolated environment (VM/container)

1. **System call tracing**
   ```bash
   # Linux
   strace -c <binary>                    # Syscall summary
   strace -e trace=open,read,write <binary>  # Specific calls

   # macOS
   dtruss <binary>                       # DTrace-based

   # Count syscalls by type
   strace -c <binary> 2>&1 | grep -E "read|write|open|close|mmap"
   ```

2. **Library calls**
   ```bash
   # Linux
   ltrace <binary> 2>&1 | head -100

   # Function call patterns
   ltrace <binary> 2>&1 | grep -E "malloc|free|memcpy|strcpy"
   ```

3. **Network behavior**
   ```bash
   # Monitor network calls (run in background)
   sudo tcpdump -i any -w /tmp/binary-traffic.pcap &
   TCPDUMP_PID=$!

   <binary>

   sudo kill $TCPDUMP_PID

   # Analyze captured traffic
   tcpdump -r /tmp/binary-traffic.pcap -nn
   ```

4. **Memory analysis**
   ```bash
   # Memory map
   pmap $(pgrep <binary-name>)

   # Heap usage over time
   valgrind --leak-check=full --track-origins=yes <binary>

   # Memory profiler
   heaptrack <binary>
   ```

**Output:** Dynamic analysis report (syscalls, library calls, network, memory patterns)
</phase>

<phase name="4" label="Security Analysis">
**Goal:** Identify security properties and vulnerabilities

1. **Security features**
   ```bash
   # ELF security features
   checksec --file=<binary>
   # Look for: PIE, NX, Canary, RELRO, ASLR

   # Manual check
   readelf -h <binary> | grep Type    # PIE if "DYN"
   readelf -l <binary> | grep "GNU_STACK"  # NX if "RW" not "RWE"
   ```

2. **Dangerous functions**
   ```bash
   # Known vulnerable functions
   objdump -d <binary> | grep -E "gets|strcpy|sprintf|strcat|system|exec"
   nm <binary> | grep -E "gets|strcpy|sprintf|strcat|system|exec"

   # Buffer operations
   objdump -d <binary> | grep -E "memcpy|memmove|strncpy"
   ```

3. **Secrets detection**
   ```bash
   # Hardcoded secrets (from strings)
   grep -E "['\"][a-zA-Z0-9]{32,}['\"]" /tmp/binary-strings.txt

   # API keys patterns
   grep -E "api.*key|secret.*key|access.*token" /tmp/binary-strings.txt -i
   ```

4. **Attack surface**
   ```bash
   # Network listening
   strace <binary> 2>&1 | grep -E "bind|listen|accept"

   # File operations
   strace <binary> 2>&1 | grep -E "open|creat|unlink"

   # Privilege operations
   strace <binary> 2>&1 | grep -E "setuid|setgid|chmod"
   ```

**Output:** Security assessment (mitigations present, vulnerabilities, attack surface)
</phase>

<phase name="5" label="Performance & Efficiency Analysis">
**Goal:** Identify computational waste and optimization opportunities

1. **Binary size breakdown**
   ```bash
   # Section sizes
   size <binary>

   # Largest sections
   readelf -S <binary> | awk '{print $5, $2}' | sort -h | tail -10

   # Bloat check
   bloaty <binary>  # If available
   ```

2. **Hot paths identification**
   ```bash
   # Profile with perf (Linux)
   perf record -g <binary>
   perf report

   # Sample-based profiling
   sudo dtrace -n 'profile-997 /execname == "<binary>"/ { @[ustack()] = count(); }' # macOS
   ```

3. **Algorithmic complexity hints**
   ```bash
   # Look for nested loops in assembly
   objdump -d <binary> | grep -E "loop|jne|jmp" | wc -l

   # Function call depth (estimate from disassembly)
   # Deep call stacks may indicate over-abstraction
   ```

4. **Memory efficiency**
   ```bash
   # Check for memory leaks
   valgrind --leak-check=full <binary>

   # Memory allocations
   ltrace <binary> 2>&1 | grep -E "malloc|calloc|realloc" | wc -l
   ```

**Output:** Performance analysis (size bloat, hot paths, memory efficiency)
</phase>

<phase name="6" label="Reverse Engineering Deep Dive">
**Goal:** Understand program logic and algorithms (if needed)

**Use advanced tools for deeper analysis:**

1. **Ghidra** - NSA's reverse engineering suite
   ```bash
   # Launch Ghidra project
   ghidra <binary>

   # Auto-analyze
   # Review decompiled C code
   # Analyze functions of interest
   ```

2. **Binary Ninja** - Modern RE platform
   ```bash
   binaryninja <binary>

   # Use high-level IL (HLIL) for understanding
   # Graph view for control flow
   ```

3. **radare2** - CLI-based RE framework
   ```bash
   r2 -A <binary>

   # Common commands:
   aaa              # Analyze all
   afl              # List functions
   pdf @ main       # Disassemble main
   VV @ main        # Visual graph mode
   ```

4. **IDA Free** - Industry standard (limited version)
   ```bash
   ida64 <binary>   # or ida for 32-bit

   # F5 for decompilation (if supported)
   ```

**Focus on:**
- Core algorithm implementation
- Data structure usage
- Code generation quality (optimization level)
- Inline vs. function calls (abstraction overhead)

**Output:** Reverse engineering report (key algorithms, logic flow, code quality)
</phase>

<phase name="7" label="First Principles Deconstruction">
**Goal:** Evaluate if binary is efficiently built for its purpose

1. **Essential functionality assessment**
   - What does this program actually do? (from syscalls, network, file I/O)
   - What's the minimal set of operations needed?
   - How much of the binary is framework/runtime vs. actual logic?

2. **Bloat analysis**
   ```bash
   # Compare binary size to functionality
   # Large binary for simple task = likely bloat

   # Check for unused code
   # If stripped binary is still large, investigate linked libraries

   # Identify framework overhead
   ldd <binary> | wc -l    # Excessive dependencies?
   ```

3. **Tech stack evaluation from binary**
   ```bash
   # Language detection from strings/symbols
   strings <binary> | grep -E "panic|goroutine" && echo "Go"
   strings <binary> | grep -E "libstd.*rust" && echo "Rust"
   strings <binary> | grep -E "PyEval|PyObject" && echo "Python"
   strings <binary> | grep -E "v8::internal|node::" && echo "Node.js"

   # Runtime overhead
   ldd <binary> | grep -E "libgo|libstd|libpython|libnode"
   ```

4. **Optimization level**
   ```bash
   # Check if optimized (look for debug symbols)
   file <binary> | grep debug

   # Optimization indicators in disassembly
   # O0: many function calls, readable
   # O2/O3: inlining, vectorization, hard to follow
   ```

**Output:** Efficiency evaluation (bloat sources, optimization level, runtime overhead)
</phase>

<phase name="8" label="Synthesize Findings">
**Goal:** Create comprehensive binary analysis report

Use template: `templates/architecture-analysis-report.md`

Include:
1. **Binary Profile** - Format, arch, size, stripped status
2. **Static Analysis** - Functions, strings, disassembly insights
3. **Dynamic Behavior** - Syscalls, network, memory patterns
4. **Security Assessment** - Mitigations, vulnerabilities, attack surface
5. **Performance Analysis** - Hot paths, bloat, memory efficiency
6. **Reverse Engineering** - Key algorithms and logic (if performed)
7. **First Principles** - Is the binary efficiently built?
8. **Recommendations** - Optimization opportunities, security hardening

Save report:
```bash
Write: analysis-reports/<binary-name>-binary-analysis-<date>.md
```
</phase>
</process>

<tools>
**Essential tools (install if missing):**
- `file`, `objdump` - Universal binary inspection
- `readelf`, `nm`, `ldd` - ELF analysis (Linux)
- `otool`, `lipo` - Mach-O analysis (macOS)
- `strings` - String extraction
- `strace`, `ltrace` - System/library call tracing (Linux)
- `dtruss` - System call tracing (macOS)
- `valgrind` - Memory analysis
- `perf` - Performance profiling (Linux)
- `tcpdump` - Network monitoring
- `checksec` - Security feature detection

**Advanced tools (optional):**
- **Ghidra** - https://ghidra-sre.org/
- **Binary Ninja** - https://binary.ninja/
- **radare2** - https://rada.re/
- **IDA Free** - https://hex-rays.com/ida-free/
- **Hopper** - https://www.hopperapp.com/ (macOS)

**Installation:**
```bash
# Debian/Ubuntu
sudo apt install binutils strace ltrace valgrind linux-perf tcpdump

# macOS
brew install binutils radare2 valgrind
```
</tools>

<safety>
**IMPORTANT: Dynamic analysis safety**
- Only execute binaries from trusted sources
- Use isolated environment (VM, container) for unknown binaries
- Disable network if analyzing potentially malicious binary
- Use read-only filesystem mounts
- Never run as root unless necessary (and never for untrusted binaries)

**Sandboxing:**
```bash
# Container isolation
docker run --rm -it --network none -v $(pwd):/analysis ubuntu
apt update && apt install binutils strace ltrace
cd /analysis && strace <binary>

# VM snapshot
# Take VM snapshot before running unknown binary
# Revert after analysis
```
</safety>

<architecture_support>
**Cross-architecture analysis:**

**x86/x86_64:** Most tools support natively
**ARM/ARM64:** Use `qemu-user-static` for emulation
```bash
qemu-arm-static <arm-binary>
qemu-aarch64-static <arm64-binary>
```

**RISC-V:** Use `qemu-riscv64-static`
```bash
qemu-riscv64-static <riscv-binary>
```

**Others (PowerPC, MIPS, SPARC):** QEMU user-mode emulation
```bash
qemu-ppc-static <powerpc-binary>
qemu-mips-static <mips-binary>
```

**Install QEMU:**
```bash
sudo apt install qemu-user-static qemu-user
```
</architecture_support>

<output_format>
Create structured markdown report using template:
`templates/architecture-analysis-report.md`

Include:
- Binary profile table (architecture, format, size, etc.)
- Assembly snippets for key functions
- Syscall/library call statistics
- Security assessment with severity ratings
- Performance metrics (size, memory, syscalls)
- Recommendations prioritized by impact
</output_format>

<success_criteria>
Analysis is complete when:
- Binary format and architecture identified
- Static analysis performed (strings, disassembly, symbols)
- Dynamic analysis completed (if safe to execute)
- Security features and vulnerabilities assessed
- Performance characteristics understood
- First principles evaluation of efficiency
- Report generated with evidence-backed findings
- All recommendations actionable and prioritized
</success_criteria>
