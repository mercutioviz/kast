# `templates/partials/` — shared template fragments

Phase A8 set up this directory as the home for Jinja partials that
both `report_template.html` (browser) and `report_template_pdf.html`
(WeasyPrint) include via `{% include "partials/<name>.html" %}`.

**Why partials in addition to `_macros.html`?** Macros (in
`../_macros.html`) are for small parameterized rendering primitives
— think functions. Partials are for larger blocks of template markup
that render the same way in HTML and PDF — think shared sections.

## Current state

A8 deliberately kept extraction conservative because:
- The two templates have legitimately different layouts (HTML has
  interactive anchor nav, PDF has a cover page with severity boxes).
- We have no end-to-end golden-output diff yet to catch subtle
  rendering regressions across the refactor.
- Phase A's rule is "preserve user-visible behavior."

So this directory starts empty. Future template work — driven by
real cases where HTML and PDF rendering converge — will populate it.

## When to add a partial here

- The same chunk of markup exists in both templates with only
  cosmetic differences (class names, heading levels).
- The chunk is large enough that copy-paste duplication is a
  maintenance hazard (rule of thumb: ≥ 15 lines).
- The chunk doesn't fit cleanly into a macro (i.e., it's structural
  markup, not a reusable rendering primitive).

## When NOT to add a partial here

- The HTML and PDF versions are structurally different (e.g.,
  severity badges vs. cover-page severity boxes — same data, very
  different markup).
- The partial would need so many parameters that the include site
  is harder to read than the original.
