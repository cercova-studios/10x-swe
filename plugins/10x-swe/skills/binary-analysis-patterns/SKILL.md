---
name: binary-analysis-patterns
description: Master binary analysis patterns including disassembly, decompilation,
  control flow analysis, and code pattern recognition. Use when analyzing executables,
  understanding compiled code, or performing static analysis on binaries.
metadata:
  skill-graph-id: plugin/10x-swe/binary-analysis-patterns
  skill-graph-uses: plugin/10x-swe/ghidra
  skill-graph-used-by: ''
---

# Binary Analysis Patterns

Resolve one assembly or decompiler ambiguity at a time. This skill supplies recognition patterns, not an analysis engine or permission to execute or modify a target.

## Workflow

1. Record the exact artifact/slice, architecture, instruction mode, OS ABI, and compiler/language context when known. Separate runtime, image, and file addresses.
2. Start from the relevant function or instruction range and its callers. Use disassembly to check pseudocode, operand widths, flags, signedness, and control flow.
3. Read only the needed section of the [pattern primer](references/primer.md):
   - **Disassembly Fundamentals:** prologues, registers, calling conventions.
   - **Control Flow Patterns:** branches, loops, jump tables.
   - **Data Structure Patterns:** indexing, layout, linked lists; LP64 versus LLP64.
   - **Common Code Patterns:** strings, arithmetic, bit operations and input preconditions.
   - **Decompilation Patterns:** variable, signature, and type recovery.
   - **Ghidra Analysis Tips / IDA Pro Patterns:** bounded interpretation of tool examples.
4. Verify the exact ABI before assigning types or return semantics. Register width alone does not establish a source type. Negative signed remainder is not a bit mask; the BSR leading-zero pattern requires nonzero input.
5. Report the locator, inferred meaning, supporting instructions/callers, and unresolved assumptions. Distinguish a plausible pattern from proven behavior. Stop when the question is answered; broad export or target execution is not the default.

Use the existing Ghidra specialist for tool setup and supported analysis operations; use the investigation controller for cross-artifact questions. Explicit application changes belong to the reverse-engineering workflow, not this primer.
