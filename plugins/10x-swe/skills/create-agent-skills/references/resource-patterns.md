# Resource patterns

Read this when selecting reusable resources or splitting a skill with several domains or providers.

## Choose resources from tasks

For each representative request, outline execution from scratch and identify repeated work:

- PDF rotation repeatedly needs the same transformation: use a tested `scripts/rotate_pdf.py` helper.
- A frontend starter repeatedly needs the same scaffold: use `assets/frontend-template/`.
- Database analysis depends on stable table relationships: use `references/schema.md`.

Scripts reduce repeated implementation and can run without loading their full source. Read them when modifying them or checking environment-specific behavior. References hold schemas, domain rules, API details, and longer examples. Assets are copied or used in deliverables, rather than loaded as instructions.

## Split by decision

Keep common workflow and selection criteria in the entrypoint. Place domain-specific detail in files such as `references/finance.md` and `references/product.md`; provider-specific procedures can use `references/aws.md` and `references/gcp.md`.

For a document skill, link form-filling details only from the form-filling decision, tracked-change rules from editing, and file-format internals from low-level repair. Give each reference a direct entrypoint link and a read condition.

For a large reference, provide a contents list and precise section or search hints. Avoid nested reference chains and duplicated procedures.

## Check useful specificity

Use a fixed command or narrow script for error-prone operations. Use pseudocode or configurable helpers when a preferred pattern admits variation. Use concise heuristics when context determines the method. Examples should teach the decision, not add another full workflow.
