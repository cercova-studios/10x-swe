# Binary Analysis Patterns

Read only the section needed for the current ambiguity. These are schematic recognition patterns, not executable patch recipes or proof of source types. Establish architecture, OS ABI, compiler/language conventions, operand widths, and input preconditions first. Independently corroborate decompiler output with instructions and callers.

## Contents

- [Disassembly Fundamentals](#disassembly-fundamentals)
- [Control Flow Patterns](#control-flow-patterns)
- [Data Structure Patterns](#data-structure-patterns)
- [Common Code Patterns](#common-code-patterns)
- [Decompilation Patterns](#decompilation-patterns)
- [Ghidra Analysis Tips](#ghidra-analysis-tips)
- [IDA Pro Patterns](#ida-pro-patterns)
- [Best Practices](#best-practices)

## Disassembly Fundamentals

### x86-64 Instruction Patterns

#### Function Prologue/Epilogue

```asm
; Standard prologue
push rbp           ; Save base pointer
mov rbp, rsp       ; Set up stack frame
sub rsp, 0x20      ; Allocate local variables

; Leaf function (no calls)
; May skip frame pointer setup
sub rsp, 0x18      ; Just allocate locals

; Standard epilogue
mov rsp, rbp       ; Restore stack pointer
pop rbp            ; Restore base pointer
ret

; Leave instruction (equivalent)
leave              ; mov rsp, rbp; pop rbp
ret
```

#### Calling Conventions

The summaries below concern ordinary integer/pointer arguments and scalar returns. Floating-point/vector arguments and returns, aggregates, hidden result pointers, varargs, and language-specific conventions need the exact platform ABI. Stack alignment is a caller obligation; these snippets do not establish the incoming stack state.

**System V AMD64 (Linux, macOS)**

```asm
; Arguments: RDI, RSI, RDX, RCX, R8, R9, then stack
; Integer return: RAX (RDX:RAX for a qualifying 128-bit integer)
; Caller-saved: RAX, RCX, RDX, RSI, RDI, R8-R11
; Callee-saved: RBX, RBP, R12-R15

; Example: func(a, b, c, d, e, f, g)
mov rdi, [a]       ; 1st arg
mov rsi, [b]       ; 2nd arg
mov rdx, [c]       ; 3rd arg
mov rcx, [d]       ; 4th arg
mov r8, [e]        ; 5th arg
mov r9, [f]        ; 6th arg
push qword [g]     ; 7th arg; ensure 16-byte RSP alignment before call
call func
```

**Microsoft x64 (Windows)**

```asm
; Arguments: RCX, RDX, R8, R9, then stack
; Shadow space: 32 bytes reserved on stack
; Return: RAX

; Example: func(a, b, c, d, e)
sub rsp, 0x28      ; Shadow space + alignment if incoming RSP mod 16 == 8
mov rcx, [a]       ; 1st arg
mov rdx, [b]       ; 2nd arg
mov r8, [c]        ; 3rd arg
mov r9, [d]        ; 4th arg
mov rax, [e]
mov [rsp+0x20], rax ; 5th arg on stack (no memory-to-memory MOV)
call func
add rsp, 0x28
```

### ARM Assembly Patterns

#### ARM64 (AArch64) Calling Convention

Generic integer-register sketch, not a full Apple/Windows/AAPCS64 contract. Platform rules differ for stack arguments, variadic calls, and reserved registers; floating-point and aggregate classification is separate.

```asm
; Arguments: X0-X7
; Return: X0 (and X1 for 128-bit)
; Frame pointer: X29
; Link register: X30

; Function prologue
stp x29, x30, [sp, #-16]!  ; Save FP and LR
mov x29, sp                 ; Set frame pointer

; Function epilogue
ldp x29, x30, [sp], #16    ; Restore FP and LR
ret
```

#### ARM32 Calling Convention

Integer-register sketch only. Confirm ARM/Thumb mode, AAPCS variant, floating-point ABI, stack alignment, and register-pair rules on the target.

```asm
; Arguments: R0-R3, then stack
; Return: R0 (and R1 for 64-bit)
; Link register: LR (R14)

; Function prologue
push {fp, lr}
add fp, sp, #4

; Function epilogue
pop {fp, pc}    ; Return by popping PC
```

## Control Flow Patterns

### Conditional Branches

```asm
; if (a == b)
cmp eax, ebx
jne skip_block
; ... if body ...
skip_block:

; if (a < b) - signed
cmp eax, ebx
jge skip_block    ; Jump if greater or equal
; ... if body ...
skip_block:

; if (a < b) - unsigned
cmp eax, ebx
jae skip_block    ; Jump if above or equal
; ... if body ...
skip_block:
```

### Loop Patterns

```asm
; for (int i = 0; i < n; i++)
xor ecx, ecx           ; i = 0
loop_start:
cmp ecx, [n]           ; i < n
jge loop_end
; ... loop body ...
inc ecx                ; i++
jmp loop_start
loop_end:

; while (condition)
jmp loop_check
loop_body:
; ... body ...
loop_check:
cmp eax, ebx
jl loop_body

; do-while
loop_body:
; ... body ...
cmp eax, ebx
jl loop_body
```

### Switch Statement Patterns

```asm
; Jump table pattern
mov eax, [switch_var]
cmp eax, max_case
ja default_case
jmp qword [jump_table + rax*8] ; schematic absolute-address table; verify layout

; Sequential comparison (small switch)
cmp eax, 1
je case_1
cmp eax, 2
je case_2
cmp eax, 3
je case_3
jmp default_case
```

## Data Structure Patterns

### Array Access

```asm
; array[i] - 4-byte elements
mov eax, [rbx + rcx*4]        ; rbx=base, rcx=index

; array[i] - 8-byte elements
mov rax, [rbx + rcx*8]

; Multi-dimensional array[i][j]
; arr[i][j] = base + (i * cols + j) * element_size
imul eax, [cols]
add eax, [j]
mov edx, [rbx + rax*4]
```

### Structure Access

This example assumes **LP64**, 4-byte `int`, 8-byte `long`/pointers, natural alignment, and no packing override (typical Unix x86-64). `d` is at offset 16 and the structure size is 24 with 8-byte alignment. Under **LLP64** (Windows x64), `long` is 4 bytes: `c` remains at offset 8, `d` moves to offset 12, and the structure size is 16 with 4-byte alignment. Check the target's ABI, packing, and actual field types rather than transferring offsets.

```c
struct Example {
    int a;      // offset 0
    char b;     // offset 4
    // padding  // offset 5-7
    long c;     // offset 8
    short d;    // offset 16
};
```

```asm
; Accessing struct fields
mov rdi, [struct_ptr]
mov eax, [rdi]         ; s->a (offset 0)
movzx eax, byte [rdi+4] ; s->b (offset 4)
mov rax, [rdi+8]       ; s->c (offset 8)
movsx eax, word [rdi+16] ; signed s->d as int (LP64 offset 16)
```

### Linked List Traversal

```asm
; while (node != NULL)
list_loop:
test rdi, rdi          ; node == NULL?
jz list_done
; ... process node ...
mov rdi, [rdi+8]       ; node = node->next (assuming next at offset 8)
jmp list_loop
list_done:
```

## Common Code Patterns

### String Operations

```asm
; strlen pattern
xor ecx, ecx
strlen_loop:
cmp byte [rdi + rcx], 0
je strlen_done
inc ecx
jmp strlen_loop
strlen_done:
; ecx contains length

; strcpy pattern
strcpy_loop:
mov al, [rsi]
mov [rdi], al
test al, al
jz strcpy_done
inc rsi
inc rdi
jmp strcpy_loop
strcpy_done:

; memcpy using rep movsb; non-overlapping ranges, direction flag clear
mov rdi, dest
mov rsi, src
mov rcx, count
rep movsb
```

### Arithmetic Patterns

```asm
; Multiplication by constant
; x * 3
lea eax, [rax + rax*2]

; x * 5
lea eax, [rax + rax*4]

; x * 10
lea eax, [rax + rax*4]  ; x * 5
add eax, eax            ; * 2

; Division by power of 2 (signed)
mov eax, [x]
cdq                     ; Sign extend to EDX:EAX
and edx, 7              ; For divide by 8
add eax, edx            ; Adjust for negative
sar eax, 3              ; Arithmetic shift right

; Separate remainder example: reload x, not the quotient above
mov eax, [x]
and eax, 7              ; unsigned x % 8, or signed x >= 0 only
; Signed C/C++ remainder truncates toward zero: -1 % 8 == -1,
; whereas masking the low three bits of -1 gives 7.
```

### Bit Manipulation

```asm
; Test specific bit
test eax, 0x80          ; Test bit 7
jnz bit_set

; Set bit
or eax, 0x10            ; Set bit 4

; Clear bit
and eax, ~0x10          ; Clear bit 4

; Toggle bit
xor eax, 0x10           ; Toggle bit 4

; Count leading zeros in a 32-bit input, ECX != 0 REQUIRED
bsr eax, ecx            ; Zero input sets ZF and leaves destination undefined
xor eax, 31             ; 31 - highest-set-bit index for nonzero input
; Handle zero separately (result 32) before using this sequence.

; Population count (requires CPU POPCNT support)
popcnt eax, ecx         ; Count set bits
```

## Decompilation Patterns

### Variable Recovery

```asm
; Local variable at rbp-8
mov qword [rbp-8], rax  ; Store to local
mov rax, [rbp-8]        ; Load from local

; Stack-allocated array
lea rax, [rbp-0x40]     ; Array starts at rbp-0x40
mov [rax], edx          ; array[0] = value
mov [rax+4], ecx        ; array[1] = value
```

### Function Signature Recovery

```asm
; Identify parameters by register usage
func:
    ; rdi used as first param (System V)
    mov [rbp-8], rdi    ; Save param to local
    ; rsi used as second param
    mov [rbp-16], rsi
    ; Identify return by RAX at end
    mov rax, [result]
    ret
```

### Type Recovery

```asm
; 1-byte operations suggest char/bool
movzx eax, byte [rdi]   ; Zero-extend byte
movsx eax, byte [rdi]   ; Sign-extend byte

; 2-byte operations suggest short
movzx eax, word [rdi]
movsx eax, word [rdi]

; 4-byte operations suggest int/float
mov eax, [rdi]
movss xmm0, [rdi]       ; Float

; 8-byte operations suggest 64-bit integer/double/pointer
; long is 8 bytes only on LP64, not LLP64
mov rax, [rdi]
movsd xmm0, [rdi]       ; Double
```

## Ghidra Analysis Tips

### Improving Decompilation

Apply type/signature changes only to a task-owned analysis project after evidence supports them; annotations can make an incorrect decompilation look convincing. Resolve addresses from the actual program, check that the function exists, and use the installed Ghidra API. The following Java fragment is schematic, not a standalone script.

```java
// In Ghidra scripting
// Fix function signature
Function func = getFunctionAt(toAddr(0x401000));
func.setReturnType(IntegerDataType.dataType, SourceType.USER_DEFINED);

// Create structure type
StructureDataType struct = new StructureDataType("MyStruct", 0);
struct.add(IntegerDataType.dataType, "field_a", null);
struct.add(PointerDataType.dataType, "next", null);

// Apply to memory
createData(toAddr(0x601000), struct);
```

### Pattern Matching Scripts

The sketch below lists references, not confirmed calls or vulnerabilities. Distinguish code calls from data references and inspect argument bounds. Use the Python dialect supported by the installed Ghidra scripting provider.

```python
# Find candidate references to selected library functions
for func in currentProgram.getFunctionManager().getFunctions(True):
    for ref in getReferencesTo(func.getEntryPoint()):
        if func.getName() in ["strcpy", "sprintf", "gets"]:
            print("Candidate reference at {}".format(ref.getFromAddress()))
```

## IDA Pro Patterns

### IDAPython Analysis

This direct-call sketch is x86-specific and incomplete: indirect calls, imports/thunks, and tail calls need separate resolution. Addresses and names are leads, not stable cross-version identities. Check API compatibility with the installed IDA version.

```python
import idaapi
import idautils
import idc

# Find all function calls
def find_calls(func_name):
    for func_ea in idautils.Functions():
        for head in idautils.Heads(func_ea, idc.find_func_end(func_ea)):
            if idc.print_insn_mnem(head) == "call":
                target = idc.get_operand_value(head, 0)
                if idc.get_func_name(target) == func_name:
                    print(f"Call to {func_name} at {hex(head)}")

# Rename functions based on strings
def auto_rename():
    for s in idautils.Strings():
        for xref in idautils.XrefsTo(s.ea):
            func = idaapi.get_func(xref.frm)
            if func and "sub_" in idc.get_func_name(func.start_ea):
                # Use string as hint for naming
                pass
```

## Best Practices

### Analysis Workflow

1. **Initial triage**: File type, architecture, imports/exports
2. **String analysis**: Identify interesting strings, error messages
3. **Function identification**: Entry points, exports, cross-references
4. **Control flow mapping**: Understand program structure
5. **Data structure recovery**: Identify structs, arrays, globals
6. **Algorithm identification**: Crypto, hashing, compression
7. **Documentation**: Comments, renamed symbols, type definitions

### Common Pitfalls

- **Optimizer artifacts**: Code may not match source structure
- **Inline functions**: Functions may be expanded inline
- **Tail call optimization**: `jmp` instead of `call` + `ret`
- **Dead code**: Unreachable code from optimization
- **Position-independent code**: RIP-relative addressing
