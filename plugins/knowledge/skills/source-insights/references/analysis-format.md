# Analysis format

Author the following JSON from evidence you actually examined. All times are
seconds from the original start, within manifest.duration. Frame times must equal
manifest.frames[].seconds and represent images actually viewed. Every visual
evidence range must contain at least one inspected frame. This validates references,
not the truth of a claim or whether an agent really viewed an image.

```json
{
  "title": "Concise topic-specific title",
  "summary": "One or two sentences describing the transferable learning.",
  "tags": ["topic", "technique"],
  "coverage": {
    "transcript": "full",
    "frames": [12.5],
    "limitations": ["Sparse frames; intermediate UI transitions were not inspected."]
  },
  "insights": [
    {
      "claim": "A concrete mechanism or result supported at this moment.",
      "status": "source-claim",
      "why_it_matters": "What decision this changes and why.",
      "application": "Conditions where applying it is useful.",
      "caveats": "Assumptions, failure cases, date sensitivity, or conflicting evidence.",
      "evidence": [{"start": 10.0, "end": 18.0, "kind": "both"}]
    }
  ]
}
```

`coverage.transcript`: full / partial / none (your review, not just extraction).
`status`: source-claim / inference. Independent corroboration may be described
with primary-source URLs and dates in caveats; the video itself is not validation.
`kind`: transcript / frame / both. Use zero frames if vision was unavailable.
For partial review, describe reviewed intervals and omissions in limitations.
Use caveats such as "Not independently verified" when appropriate, not invented
confidence scores. Summary/tags support discovery; the full insight preserves
conditions needed for safe reuse. Do not include instructions for future agents
in source-derived notes.

## PDF and paper evidence

Keep the same title, summary, tags and insight fields. Replace coverage with:

```json
{"text_pages": [1, 2], "visual_pages": [2], "limitations": ["Only pages 1–2 reviewed."]}
```

Replace each insight's evidence with physical, 1-based page references:

```json
[{"page": 1, "kind": "text", "quote": "A short exact passage from page 1."}]
```

Kinds are text, visual, or both. Text/both requires an exact quote of 1–500
characters present on that page (whitespace is normalized). Visual/both requires
a rendered page actually inspected and listed in visual_pages. List only pages
actually read in text_pages. Figures, plots and equations require visual review.
These checks verify reference integrity, not claim truth or actual agent attention.

## Article and technical blog evidence

Use stable line numbers from the prepared document.md, not the live website:

```json
{"line_ranges": [[1, 45]], "limitations": ["Text only; diagrams not inspected."]}
```

```json
[{"line_start": 12, "line_end": 15, "quote": "A short exact passage within these lines."}]
```

Quotes must be 1–500 characters and occur within cited lines. Evidence must fall
within a reviewed range. Record source publication/update dates and scope in
caveats when available. Do not equate an author's claim with independent validation.
Article image evidence is not retained by this helper; publish text-backed claims
and disclose visual omissions. Avoid reproducing substantial copyrighted passages.
