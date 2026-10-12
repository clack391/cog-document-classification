# Taxonomy

Owner: Precious.

## What's here

| File | What it is | Who reads it |
|---|---|---|
| `document-taxonomy.frame.md` | The taxonomy as a Frame (Frame Spec v0.2): types, boundary rules and the tag vocabulary | People, and any model or Cog given the Frame |
| `questions.json` | A draft of the same taxonomy as System One questions | The model behind the Cog. Apart from the document text, it is all the model sees. |

`questions.json` is a draft. It replaces `context/questions.json` once the input
and output schemas are agreed. Until then, `context/` still holds Smith's starter
question set, so the package keeps passing its checks.

Keep the two files in sync: change one, change the other. When `questions.json`
moves into `context/`, a test will compare its types and tags with the Frame's.

## How the Frame maps to the questions

| In the Frame | In `questions.json` |
|---|---|
| Type definitions, signals and boundary rules | Option descriptions of the `document_type` choice question |
| Each tag in the Tag Vocabulary | One yes/no question named `tag_<tag>` |
| The rule on garbled or fragmentary text | The `text_legible` yes/no question |
| Contradiction rules, review rules and thresholds | Not questions: policy in `decide` in `src/task_logic.py` |

The manifest lists the Frame under `frames`. The suite carries that field as
metadata and does not load Frames into a decision Cog, so the questions remain
the operative copy.

The questions use only `choice` and `noul`. When they move into `context/`, set
`required_features = ["choice", "noul"]` in the manifest's
`workbench_composition`.

## Thresholds

These are placeholders until the benchmark sets tune them, separately for each
model.

| Check | Threshold | Result |
|---|---|---|
| `document_type` confidence | 0.85 | below it: review |
| Tag probability | 0.7 | below it: tag not applied |
| `text_legible` probability | 0.5 | below it: review |
| Type-tag contradiction | 0.9 | at or above it, for another type: review |
| Invoice amount check (`contains_financial_amounts`) | 0.3 | below it, on an invoice: review |

## Working assumptions to confirm

These are marked in the Frame. Each needs a yes or a different rule.

1. The filename is not sent to the model.
2. Pro-forma invoices and credit notes are `invoice`. Receipts and statements are `other`.
3. Offer letters and unsigned contract templates are `contract`. Published terms of use are `other`.
4. A cover letter on its own is `other`. Exported network profiles are `resume`.
5. Sales enquiries are `other`. A support reply without the customer's request is `support_ticket`.
6. The two contradiction rules.
7. The final tag list: drop any tag nobody will route on.

## Validation

- **The Frame's frontmatter:** check it with `frame_validator.py` from the Frames toolkit.
- **`questions.json`:** checked by the System One contract, `src/system_one_contract.py`. Once it is in `context/`, `pixi run derive-schema` and `pixi run test` check it too.
- **The content:** an acceptance test on labeled sample documents. That is step 8 of the Frame playbook, and it is the same work as the benchmark set.
