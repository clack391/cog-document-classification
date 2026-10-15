---
type: cog [0.1]
name: cog-document-classification
description: "Decision Cog. Classifies one business document as an invoice, contract, resume, support ticket, bank statement or other, with tags and the model confidence, and flags uncertain or unreadable documents for review. A System One model answers its typed questions; its code makes the decision."
version: "0.1.0"
license: Apache-2.0
publisher: OpenTeams
manifest: pixi.toml
manifest_schema: openteams/cog-manifest [0.1]
---

# Document Classification

## Purpose

Classifies one business document as an invoice, contract, resume, support ticket, bank statement or other, with tags and the model confidence, and flags uncertain or unreadable documents for review.

It is the front door for incoming documents. Before a downstream workflow can
process an invoice, route a ticket or assess a candidate, it needs to know
what the document is. This Cog gives it one type, tags from a fixed
vocabulary and the model's confidence, so the workflow can route on them. When
the type can't be assigned reliably, the Cog says so and gives its reasons
instead of guessing.

A run is done when the result is either `classified`, with one type, or
`needs_review`, with no type and at least one stated reason.

The types, tags and boundary rules are defined in the taxonomy Frame,
[`taxonomy/document-taxonomy.frame.md`](taxonomy/document-taxonomy.frame.md).
Where this file and the Frame disagree, the Frame is right.

## Supported work

**Input.** One document: the caller's `document_id` and the document's
extracted text (`context/input-schema.json`). The `document_id` is echoed in
the result and never sent to the model. The filename is not part of the input,
because filenames are often wrong and can contain personal data. Text that is
empty or only whitespace is refused with an input error, and so is text over
100,000 characters or a `document_id` over 200 characters.

**Questions.** A System One model answers 18 questions about the text,
declared in `context/questions.json`:

| Question | Type | Asks |
|---|---|---|
| `document_type` | choice: `invoice` / `contract` / `resume` / `support_ticket` / `bank_statement` / `other` | What the document is for, judged by its purpose, not its topics |
| `text_legible` | noul | Does the text read as a coherent document rather than garbled OCR output or fragments? |
| `tag_<tag>`, one per tag | noul | Does this tag's statement clearly hold? |

The 16 tag questions cover these tags:

- **General tags**, which can apply to any type: `contains_personal_data`,
  `contains_financial_amounts`, `time_sensitive`, `signed`,
  `draft_or_template`, `multiple_documents`, `non_english`.
- **Type tags**, reported only with their own type:
  - `invoice`: `invoice_reminder`, `invoice_credit_note`;
  - `contract`: `contract_nda`, `contract_employment`, `contract_amendment`;
  - `support_ticket`: `ticket_urgent`, `ticket_complaint`, `ticket_billing`,
    `ticket_bug_report`.

  `resume`, `bank_statement` and `other` have no type tags.

**Decision.** `decide` in `src/task_logic.py` turns the answers into the
result. It takes the `document_type` choice as the type, unless one of these
review rules applies:

| Rule | Threshold | Flag |
|---|---|---|
| The type's confidence is below the minimum | `MIN_TYPE_CONFIDENCE` = 0.85 | `low-confidence` |
| `text_legible` is below the minimum | `MIN_LEGIBLE` = 0.5 | `illegible-text` |
| A type tag for a different type than the chosen one is this strong | `CONTRADICTION` = 0.9 | `signals-disagree` |
| The type is `invoice` but `contains_financial_amounts` is below the minimum | `INVOICE_MIN_AMOUNTS` = 0.3 | `invoice-without-amounts` |

The confidence is the `document_type` answer's confidence, not the top
option's probability.

A tag applies when its answer is at or above `TAG_THRESHOLD` = 0.7. A
classified document gets the general tags and its own type's tags that pass.
A document in review gets only the general tags that pass.

These thresholds are provisional starting values. They'll be tuned on the
[benchmark set](benchmarks/README.md) (#8), against the targets in
`benchmarks/targets.json`.

**Output.** The result's `decision` holds:

- `document_id`;
- `status`: `classified` or `needs_review`;
- `document_type`: the type, or `null` in review;
- `confidence`;
- `tags`;
- `flags`;
- `reasons`, as plain statements of the evidence.

The payload also carries every typed answer and `answered_by`, so any result
can be traced and replayed. `context/output-example.json` shows a complete
result.

**Review: flag and route.** A document the Cog is unsure of is marked
`needs_review`, with no type, its flags and its reasons. `check_output` also
reports it as a `needs-review` warning, so no workflow or Gate can pass it as
clean. Whichever workflow uses the result sends it to a person. The Cog itself
never pauses for a person, and there is no Op with a human approval Gate.
Who reviews is still to be named.

`other` is a real type for documents outside the taxonomy. It is never used
as a fallback when the Cog is unsure. An unsure result goes to review instead.

**Guards.** The Frame's Guards section defines five checks that every result
should pass. They're independent of this Cog's code:

| Guard | Checks | On failure |
|---|---|---|
| `no-document-text` | The result repeats no passage of the document | Fail |
| `no-personal-identifiers` | The result holds no email addresses, phone, card or IBAN numbers, or US Social Security numbers. The caller's own document ID isn't checked, as long as it matches the input. | Fail |
| `known-vocabulary` | Types and tags come from the Frame, type tags appear only with their own type, and a result in review has no type and at least one reason | Fail |
| `review-is-visible` | A result in review is reported as a warning | Fail |
| `calibrated-answers` | The answers came from a calibrated System One model, not an LLM | Warn |

A failed Guard holds the result back and sends the document to a person. It
never repairs the result. The Op layer can't run Guards yet, and
`ask-composed` doesn't run them either, so a live result is checked only when
the caller runs `guards/result_guard.py` on it. CI runs them on the sample
result for every push, and every benchmark run checks every document.

## Unsupported work

- **No content fields.** The Cog doesn't extract invoice numbers, amounts,
  dates, party names or any other field from the document (decision 3). That
  needs a model that writes text, and it's left to the specialised Cogs
  downstream. The file and extraction metadata from decision 3 (file type,
  page count, size, sha256 and whether OCR was used) arrives with file input
  in Phase 2.
- **No actions outside its own result.** The Cog is read-only. It never sends
  a message or modifies the source document or any other data. The manifest
  declares this in `prohibits` (`send_external_message`,
  `modify_source_data`). Today the prohibition is structural, because the Cog
  has no tools that could do these things.
- **No decisions that need a person.** It doesn't approve, pay, reject or
  route a document, and it doesn't choose who reviews one. It sets
  `needs_review`, and the workflow and a person decide what happens next.
- **No more than one type.** A file holding several documents is classified
  by its main one and tagged `multiple_documents`. If no document is clearly
  the main one, it should go to review. No rule enforces this yet: it relies on
  the model being unsure of the type, so that the confidence falls below
  `MIN_TYPE_CONFIDENCE` (#19).
- **No new types or tags.** Only the Frame's six types and 16 tags are used.
- **No inferences about people.** It doesn't infer age, gender, ethnicity,
  religion, health, disability or any other protected characteristic.
- **No file input yet.** Today the caller supplies the extracted text.
  Reading PDF and image files, with OCR for scans, comes in Phase 2. The final
  input format is decision 4.

## Who answers

The manifest requires the `system-one/decisions` capability and names no
default satisfier. A host admits one of:

- **cog-typesafe** — TypeSafe's Jev, a System One model trained for calibrated
  decisions (`answer_source: system-one-model`); cloud locality, TypeSafe API key.
- **cog-system-one-adapter** — TypeSafe's MIT-licensed System One adapter
  asking an admitted OpenAI-compatible model (for example local cog-qwen) for
  the same typed answers (`answer_source: llm-adapter`). Same shape, not the
  same meaning: LLM-stated probabilities are not calibrated decisions.

Every payload records `answered_by.model` and `answered_by.answer_source`, and
the envelope binding carries the host's full composition provenance.

`decide` isn't told which model answered, so the same thresholds apply to
every provider for now. Treat answers from the adapter as weaker evidence.
The `calibrated-answers` Guard warns when an LLM answered. Which provider we
use is decision 2.

## Using it

```bash
pixi install
pixi run check                                            # self-check, model-free
pixi run prepare -- --bundle examples/sample-bundle.json  # the turn, no call
pixi run replay -- --bundle examples/sample-bundle.json --result examples/sample-result.json
pixi run export-fixtures -- --run /path/to/run --step STEP_ID --name thresholds  # STEP_ID: the Op step that ran this Cog
pixi run test                                             # model-free suite
```

Live decisions: admit a System One binding in Workbench, then from
cog-workbench run
`pixi run suite -- activate-composition --context cog-document-classification --binding-id ID --revision N`,
and here `pixi run ask-composed -- --request bundle.json`.

`examples/sample-result.json` is an illustrative fixture (model
`illustrative-fixture`), not a recorded model response. The tests use it to
exercise the decision policy.

After editing `context/questions.json`, run `pixi run derive-schema` so
`$defs.answers` in the output schema matches the questions; `check` refuses
drift. Results are **envelope v1** (see cog-smith/ENVELOPE.md); `ok: true`
may carry problems, and a Gate decides.

## Where the machinery came from

`src/cog_core.py`, `src/cog_cli.py` and `src/system_one_contract.py` are
shared cog-smith decision-cog machinery — do not edit them here; `smith check`
verifies the copies. `scripts/composed_usage.py` is Workbench's canonical
composed-usage adapter. This Cog's identity lives in its manifest
(`pixi.toml`), `context/`, and `src/task_logic.py`.
