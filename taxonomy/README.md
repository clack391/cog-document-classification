# Taxonomy

Owner: Precious.

## What's here

[`document-taxonomy.frame.md`](document-taxonomy.frame.md) is the taxonomy as a
Frame (Frame Spec v0.2): the types, boundary rules and tag vocabulary. It is the
source of truth.

The Cog uses it in three places:

| Where | What it holds |
|---|---|
| `context/questions.json` | The questions the model answers. Apart from the document text, they are all the model sees. |
| `src/task_logic.py` | The decision policy: thresholds, review, contradictions, and which tags are reported |
| `context/output-schema.json` | The types and tags a result may contain |

`tests/test_frame_sync.py` fails whenever these disagree with the Frame on the
types or the tags. Change the Frame first, then the rest, and run `pixi run test`.

## How the Frame maps to the Cog

| In the Frame | In the Cog |
|---|---|
| Type definitions, signals and borderline cases | Option descriptions of the `document_type` question |
| Each tag in the Tag Vocabulary | One yes/no question named `tag_<tag>` |
| The rule on garbled or fragmentary text | The `text_legible` question |
| Review, contradiction and tag-reporting rules | `decide` in `src/task_logic.py` |
| "Not the filename" | `state` sends only the text |

The manifest also lists the Frame under `frames`. The suite carries that field
as metadata but does not load Frames into a decision Cog.

## Thresholds

These are placeholders until the benchmark sets tune them. They are constants
at the top of `src/task_logic.py`.

| Constant | Value | Rule |
|---|---|---|
| `MIN_TYPE_CONFIDENCE` | 0.85 | Below it, the document goes to review |
| `TAG_THRESHOLD` | 0.7 | At or above it, the tag applies |
| `MIN_LEGIBLE` | 0.5 | Below it, the document goes to review |
| `CONTRADICTION` | 0.9 | A type tag this strong for another type sends the document to review |
| `INVOICE_MIN_AMOUNTS` | 0.3 | An invoice whose amounts answer is below it goes to review |

**One set of thresholds for every model, for now.** The machinery calls
`decide(bundle, answers)` without saying which model answered, so `decide`
cannot apply a different threshold to Jev and to an LLM. The options are:
- choose the thresholds for whichever provider we deploy;
- have `check_output` add a warning for LLM-answered results;
- ask cog-smith to pass `answered_by` to `decide`.

## Decisions

- **12 Oct 2026:** all working assumptions confirmed by Precious: the
  filename, the borderline cases, the contradiction rules, and the 16-tag
  vocabulary.
- **12 Oct 2026:** type-tag questions now describe a document of their own
  type, for example "a support request about billing" rather than "about
  billing". An invoice would otherwise answer yes to the billing tag and trip
  the contradiction rule.
- **13 Oct 2026:** `bank_statement` added as a sixth type: bank and credit
  card statements and transaction-history exports. It has no type tags. The
  Frame is now v0.3.0.
- **13 Oct 2026:** Precious confirmed the bank statement boundaries: supplier
  statements of account, investment, pension and loan statements, and payslips
  are all `other`. No type tags for bank statements, and no extra review rule
  for a bank statement without amounts. The Frame is now v0.3.1, with no open
  working assumptions.

## Validation

- **The Frame's frontmatter:** check it with `frame_validator.py` from the Frames toolkit.
- **The questions, the policy and the sync with the Frame:** `pixi run test`.
- **The content:** an acceptance test on labeled sample documents. That is step 8 of the Frame playbook, and it is the same work as the benchmark set.
