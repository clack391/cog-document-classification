# Benchmark set

Owner: Precious. Tracking issue: #7. Threshold tuning: #8.

The benchmark set has three jobs:
1. **Acceptance test for the taxonomy Frame:** does the Cog classify documents
   the way [the Frame](../taxonomy/document-taxonomy.frame.md) says it should?
2. **Threshold tuning:** turn the 0.85 confidence threshold from a placeholder
   into a number backed by evidence.
3. **Regression tests:** real answers, saved and replayed, keep later changes
   honest.

## Rules

- **Synthetic or public documents only.** Nothing real goes in this folder, in
  the repo, or through AI tools; Trent said "no data in the Cog", and Inessa
  said "nothing sensitive to Anthropic".
- **Contact details must be fictional.** Use reserved ones only:
  - `example.com`, `example.org` or `example.net` email addresses;
  - UK Ofcom drama numbers such as `020 7946 0xxx`, `0161 496 0xxx` or `07700 900xxx`;
  - US `555-0100` to `555-0199`.

  The repository Guard scans this folder and fails on anything else that
  looks like personal data.
- **Other details must not be real either.** UK postcodes start with `X`,
  which no real postcode does, so no address exists. German postcodes start
  with `00`, which none does. There are no company registration numbers or
  sort codes, and the VAT numbers fail their check digits. Organisation names
  are invented too: before using a name for a bank, credit union, building
  society or payment provider, search for it, so that no made-up statement
  appears under a real institution's name.
- **Public documents need a licence** that allows it, recorded in `source` as
  `public:<licence>`. They go in `benchmarks/external/`, which Git ignores, and
  labels point at them as `external/<file>`. Synthetic documents go in
  `documents/`, and the label check enforces that split. When we adopt the
  first public dataset, add a download script so others can fetch the same
  files; a public file that hasn't been downloaded shows up as a label
  problem.

## What's in it

The set has 94 synthetic text documents. They take the Cog's current
input, plain text; file versions (PDF, DOCX, scans) come with extraction (#3).

| Group | Documents | What it checks |
|---|---|---|
| Clear examples | 61: 11 or 12 for each of the five business types, and 2 for `other` | The basic definitions of all six types, and every type tag, across many formats and languages |
| Frame rules | 33, covering all 30 rules (the unclear-type, garbled-text and multiple-documents rules have two each) | See below |

The 33 rule documents include:
- every boundary and borderline case in the Frame, such as a pro-forma
  invoice, offer letter, sales enquiry, supplier statement and payslip;
- hard cases: OCR noise, German text, an invoice with an unrelated page
  attached, and a CV followed by its cover letter, which is still a résumé;
- **5 that should go to review:**
  - an invoice, a bank statement page and a support ticket in one file, none
    of them the main one;
  - garbled text, and a near-empty page;
  - a note whose attachment is missing;
  - a page that reads half invoice, half bank statement.

In the 94 documents, the expected outcomes are 18 invoices, 14 contracts, 13
résumés, 15 support tickets, 14 bank statements, 15 `other` and 5 reviews, so
`other` is 16% of the set. The tune split has 61 documents and the test split
33. Every tag in the Frame is expected in at least one document.

The clear examples cover different formats and situations, for example:
- **invoices:** freelance, subscription, final notice, draft, French;
- **contracts:** employment, lease and extension, loan, e-signed, Spanish, not yet signed;
- **résumés:** graduate, career changer, anonymised, German, US;
- **tickets:** chat transcript, phone log, email thread, French;
- **bank statements:** business, joint, payment provider, ATM mini statement,
  German, US, and a three-page statement.

The people and companies recur across documents, and their details agree:
the same address, account and payments wherever they appear.

**Still to add:** very long documents, which test trimming once extraction
exists (#3).

## Labeling: `labels.csv`

One row per document:

| Column | Meaning |
|---|---|
| `id` | Lowercase, with hyphens. Not `run`, and not starting with `report`. |
| `file` | `documents/<file>` for synthetic documents, `external/<file>` for public ones |
| `expected` | The type the Cog should assign, or `needs_review` |
| `alternatives` | Other types that are also acceptable, separated by `;`. Only for honestly ambiguous documents. |
| `tags` | Tags that clearly apply, separated by `;` |
| `optional_tags` | Tags that may or may not apply; they're never counted as right or wrong |
| `frame_rule` | `type:<type>` for a clear example, or the Frame rule it tests (`REQUIRED_RULES` in `bench.py`) |
| `split` | `tune` (used to choose thresholds) or `test` (used only to report them) |
| `source` | `synthetic`, or `public:<licence>` |
| `notes` | Why the label is what it is |

The sheet can be edited in a spreadsheet. Excel's "CSV UTF-8" format
works, but keep it comma-separated: some regional settings save with
semicolons, and the check says so. Documents must be UTF-8 text.

Check the labels with:

```bash
pixi run python benchmarks/bench.py
```

The check enforces several rules:
- every Frame rule has at least one document, and every type has at least two clear examples;
- every tag is expected in at least one document, so its precision and recall can be measured;
- tags must fit the expected type;
- an invoice must state amounts;
- every file must exist.

When the Frame's rules change, update `REQUIRED_RULES` and `RULE_PHRASES` in
`bench.py`. `RULE_PHRASES` links each rule to its wording in the Frame. A test
fails if that wording disappears from the Frame, or if the Frame gains a rule
bullet that no benchmark rule covers. Tagging and signal rules are covered by
the policy tests instead.

**Second labeler:** ideally Francis labels about 20 documents without looking
at these labels first. Wherever you disagree, the Frame needs a clearer rule.
The 46 clear examples added on 15 October were labeled blind a second time,
from the Frame alone. The types agreed on all 46, and no tag was expected by
one labeler and missing for the other. Each of the 6 borderline points it raised
was reviewed: one tag became optional, one document got `other` as an
alternative type, one document was made clearer, and three labels stayed as
they were.

## Targets

Set in `targets.json`; changing them is a policy decision.

| Target | Value | Meaning |
|---|---|---|
| Silent error rate | ≤ 2% | Documents given a **wrong** type **without** going to a person |
| Review rate | ≤ 15% | Documents that need a person: review, blocked by a Guard, or failed |

## Running it

**Live**, once a model provider is activated (#6):

```bash
pixi run python benchmarks/run.py live --name jev-2026-10-20
pixi run python benchmarks/score.py benchmarks/results/jev-2026-10-20 --split tune
```

**From saved answers**, with no model: put one `<id>.json` per document in a
folder, either a System One result or a saved envelope, then run:

```bash
pixi run python benchmarks/run.py replay --answers path/to/answers --name replay-1
pixi run python benchmarks/score.py benchmarks/results/replay-1
```

Each run writes `benchmarks/results/<name>/`, which Git ignores because it
contains machine-specific details. It holds each document's result envelope,
the Guards' report on it, and `run.json`. `run.json` records the Cog version
and fingerprints of the labels, the decision code, the Frame and the output
Guards. Line endings don't count, so a Windows checkout matches. A run name is
never reused. The scorer adds `report.md` and `report.json`.

The live tests never call a model; they use a fake subprocess, so
`pixi run test` stays free even after a provider is activated.

## What the report shows

- **Silent errors,** listed by document, with an upper bound. With only a few
  documents, "0 of 40" doesn't prove the rate is zero; the report says how
  high it could be at 95% confidence.
- **How many documents went to a person,** and how many clear documents were
  sent to review unnecessarily.
- **Accuracy by type,** and a confusion table showing where mistakes go.
- **Precision and recall for each tag.** Optional tags are ignored, and only
  tags the result could report are counted.
- **Calibration:** at each confidence level, how often the model's top type was
  right.
- **A threshold sweep.** It re-runs the Cog's own decision code on the saved
  answers at each threshold from 0.50 to 0.95, and checks every changed
  decision with the Guards again. It recommends the lowest review rate that
  meets the silent error target. Choose on the **tune** split,
  then confirm on the **test** split.
- **Results by model,** when a run mixes models.

Every run's answers are also checked by the output Guards. A result a Guard
blocks counts as going to a person, never as a silent error. If a Guard report
is missing, the scorer runs the Guards again rather than trusting the result.

The report starts with a warning when it may not describe the run as it
happened:
- the labels, the decision code, the Frame or the output Guards changed after the run;
- the run has no fingerprints;
- Guard reports had to be rerun.
