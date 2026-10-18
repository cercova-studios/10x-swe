# Code rewrite examples

Read this when a requested change requires structural rewriting. Select an
explicit task-owned path, inspect the proposed diff, and run the affected checks.
`--rewrite` previews changes; `--interactive` or `--update-all` applies them.

A syntactic match does not prove equivalent behavior. In particular,
`$PROP && $PROP()` and `$PROP?.()` differ for non-null falsy values such as `0`:
the former short-circuits and the latter throws. Use that rewrite only when the
value is nullish or callable and evaluating it again has no side effects.
Assignment swaps and lambda-to-function transformations also need task-specific
semantic checks. Partial YAML snippets need an explicit `id` and `language`.

## Rewriting Code with ast-grep

ast-grep is a powerful AST-based tool that can search for code patterns and transform them into new code. It works like a syntax-aware sed/grep that understands code structure rather than just text.

### Method 1: Command Line with `--rewrite`

The simplest approach is using the `--rewrite` (or `-r`) flag directly in your terminal:

```bash
ast-grep run --pattern 'foo' --rewrite 'bar' --lang python
```

This previews identifier replacements. Apply them only to the approved path after checking the diff. Another example:

```bash
# Convert old-style property checks to optional chaining
ast-grep -p '$PROP && $PROP()' --rewrite '$PROP?.()' --interactive -l ts ./src
```

**Key flags:**

- `--interactive` or `-i`: Review each change before applying
- `--update-all` or `-U`: Apply all changes without confirmation

### Method 2: YAML Rules with `fix`

For more complex transformations, use YAML rule files with the `fix` field:

```yaml
id: change_def
language: Python
rule:
  pattern: |
    def foo($X):
      $$$S
fix: |-
  def baz($X):
    $$$S
```

Run with: `ast-grep scan -r rule.yml ./src`

### Meta-Variables

Meta-variables are the key to powerful rewrites. They act like capture groups in regex:

| Meta-variable | Matches                                            |
| ------------- | -------------------------------------------------- |
| `$NAME`       | Any single AST node (expression, identifier, etc.) |
| `$$$ITEMS`    | Multiple nodes (like function arguments)           |

**Example** — Swapping assignment sides:

```yaml
rule:
  pattern: $X = $Y
fix: $Y = $X
```

Transforms `a = b` into `b = a`.

### Indentation Sensitivity

ast-grep preserves indentation in rewrites. If your fix template has indentation, it's maintained relative to the original code position:

```yaml
rule:
  pattern: '$B = lambda: $R'
fix: |-
  def $B():
    return $R
```

### Expanding the Match Range with FixConfig

Sometimes you need to delete surrounding characters (like commas). Use `FixConfig` with `expandStart` and `expandEnd`:

```yaml
rule:
  kind: pair
  has:
    field: key
    regex: Remove
fix:
  template: ''
  expandEnd: { regex: ',' } # Also deletes trailing comma
```

This removes the matched node _plus_ any trailing comma.

### Advanced Features: Rewriters

For complex multi-node transformations, use `rewriters` to process lists of matched nodes:

```yaml
id: barrel-to-single
language: JavaScript
rule:
  pattern: import {$$$IDENTS} from './module'
rewriters:
  - id: rewrite-identifier
    rule:
      pattern: $IDENT
      kind: identifier
    transform:
      LIB: { convert: { source: $IDENT, toCase: lowerCase } }
    fix: import $IDENT from './module/$LIB'
transform:
  IMPORTS:
    rewrite:
      rewriters: [rewrite-identifier]
      source: $$$IDENTS
      joinBy: "\n"
fix: $IMPORTS
```

This converts barrel imports like `import { A, B } from './module'` into individual imports.

### Workflow Summary

1. **Find**: Use patterns to match AST nodes
2. **Capture**: Meta-variables (`$VAR`, `$$$ARGS`) capture matched content
3. **Transform**: Optionally process captured content (case conversion, regex replacement)
4. **Patch**: Replace matched nodes with the `fix` template

### Tips

- Use single quotes on command line to prevent shell expansion of `$`
- Bind every metavariable used by a fix and inspect the rendered output; missing bindings are not safe defaults.
