# cog-document-classification

A Cog that classifies one incoming business document, built on the
[cogcloud-ai Cog / Op Builder suite](https://github.com/cogcloud-ai/cog-op-builder).

A System One model answers a fixed set of typed questions about the document's
text. The Cog's own code then assigns one type (`invoice`, `contract`,
`resume`, `support_ticket`, `bank_statement` or `other`), adds tags from a fixed vocabulary, and
reports the model's confidence. Any document it cannot classify reliably is
marked `needs_review`, with reasons.

For now the Cog takes the document's extracted text. Reading PDF and image
files, with OCR for scans, comes in Phase 2.

It is a **decision Cog**, created with cog-smith's decision template
(`smith new --class decision`). The model answers narrow questions; the policy
(thresholds, tags, escalation) is plain code in `src/task_logic.py` that we can
read and test.

## Status

Phase 1, in progress. The package passes Smith's checks and its offline tests
on the suite's current pins, and CI runs both on Linux and macOS for every push.

**What works**
- [`COG.md`](COG.md), the human-readable contract: what the Cog decides, its
  questions and thresholds, the review rules, the Guards, and what it doesn't
  do.
- The confirmed taxonomy: the [Frame](taxonomy/document-taxonomy.frame.md) and
  the 18 questions in `context/questions.json` built from it.
- A first decision policy in `src/task_logic.py`:
  - the type is assigned at confidence 0.85 or above, and tags at 0.7;
  - low confidence, illegible text or contradicting answers send the document
    to review;
  - review is also reported to workflows as a warning.
- Tests that keep the Frame, the questions, the policy and the output schema in
  agreement.
- Guards that check every result independently, and a repository Guard. See
  [Guards](#guards).
- The [benchmark set](benchmarks/README.md): 47 labeled synthetic documents
  covering every Frame rule and tag, with a runner, a scorer and a threshold sweep. It
  is checked offline today and runs live once a model is connected.
- cog-workbench recognises the Cog, and both model providers (TypeSafe's Jev and
  the System One adapter) match its requirements. Neither is set up yet;
  choosing one is decision 2.

**What is provisional**
- The input is the document's extracted text. File input and extraction come
  in Phase 2, and the final input format is decision 4.
- The output schema has no metadata fields yet. Decision 3 settled what they
  are (file type, page count, size, sha256, and whether OCR was used), and they
  arrive with file input in Phase 2.
- The thresholds are placeholders until the benchmark sets tune them.

**Review works by flagging (decision 6):** a document the Cog is unsure of is
marked `needs_review` with its reasons and a warning, and whichever workflow
uses the result sends it to a person. Who reviews is still to be named.

See the [proposal](docs/proposal.md) for the plan, the phases and the open
decisions.

## Layout

| Path | What it is | Owner |
|---|---|---|
| `taxonomy/` | The taxonomy Frame (the source of truth) and its notes | Precious |
| `context/questions.json` | The questions the model answers, built from the Frame | Precious |
| `src/task_logic.py`: `decide` and the thresholds | The confidence and review policy | Precious |
| `tests/test_policy.py`, `tests/test_frame_sync.py` | Tests for the policy and the taxonomy | Precious |
| `guards/` | The output Guards and the repository Guard | Precious |
| `tests/test_guards.py` | Tests for the Guards | Precious |
| `benchmarks/` | Labeled synthetic documents, the runner, the scorer and the targets | Precious |
| `tests/test_benchmarks.py` | Tests for the benchmark set and its scoring | Precious |
| `COG.md` | The human-readable contract | Francis |
| `pixi.toml`, `pixi.lock` | Environment, `[tool.cog]` manifest and pinned dependencies for Linux x86-64 and Apple Silicon | Francis |
| `context/input-schema.json`, `context/output-schema.json` | The input and output contracts | Francis, with Precious for the decision fields |
| `src/task_logic.py`: `check_input` and `state` | Input checks and the extraction hookup | Francis |
| `tests/test_cog.py` | Package and contract tests | Francis |
| `docs/` | The proposal and notes on the suite | Both; Precious leads stakeholder updates |

Every other file in `src/` is Smith machinery: never edit it. All tests run
offline and need no model.

## Getting started

You need Git, Python 3.11 or newer, and [Pixi](https://pixi.sh). The suite's
CI uses Pixi v0.69.0. This Cog must sit next to the suite's components in one
workspace folder, because its live entry point looks for `../cog-workbench`.

```bash
mkdir cog-workspace && cd cog-workspace
git clone https://github.com/cogcloud-ai/cog-op-builder.git
git -C cog-op-builder checkout 71834ce2f28a37cfa65e7b19a3c9de80dc688f86
python3 cog-op-builder/scripts/bootstrap.py
git clone https://github.com/clack391/cog-document-classification.git
cd cog-document-classification
pixi install
pixi run test
pixi run check
```

Smith's full package check, run from `cog-smith`:

```bash
cd ../cog-smith
pixi install
pixi run check -- ../cog-document-classification --tests
```

Working without a model, from this Cog's folder:

```bash
cd ../cog-document-classification
pixi run prepare -- --bundle examples/sample-bundle.json
pixi run replay -- --bundle examples/sample-bundle.json --result examples/sample-result.json
```

`prepare` shows what would be sent to the model. `replay` decides from saved
answers.

Live runs need a model provider admitted in cog-workbench: TypeSafe's Jev in the
cloud, or local Qwen through the System One adapter. Which one we use is still
open; see the proposal. Until a provider is activated, `pixi run ask-composed`
stops with an error that `.op-composition.json` is missing. That file is
written when Workbench activates a provider for this Cog.

## Guards

Guards check every result independently of the Cog. They read the
[Frame](taxonomy/document-taxonomy.frame.md), the input and the result, and
nothing from the Cog's own code. The Frame's Guards section lists each check
and what happens when it fails:

| Guard | Checks | On failure |
|---|---|---|
| `no-document-text` | The result repeats no passage of the document | Fail |
| `no-personal-identifiers` | The result holds no email addresses, phone, card or IBAN numbers, or US Social Security numbers. The caller's own document ID isn't checked, as long as it matches the input. | Fail |
| `known-vocabulary` | Types and tags come from the Frame, and a result in review has no type | Fail |
| `review-is-visible` | A result in review is reported as a warning | Fail |
| `calibrated-answers` | The answers came from a calibrated System One model, not an LLM | Warn |

A separate repository Guard checks every file Git doesn't ignore, including new
ones before they're committed. It looks for credentials, keys and `.env` files,
and for personal identifiers in sample, test and benchmark data. Reserved
fictional contact details (`example.com` emails, UK drama numbers, US
555-01xx) are allowed in that data.
CI runs both on every push. The Op layer can't run Guards yet, so for now they
run as scripts:

```bash
pixi run python guards/repo_guard.py
pixi run replay -- --bundle examples/sample-bundle.json --result examples/sample-result.json > envelope.json
pixi run python guards/result_guard.py --bundle examples/sample-bundle.json --envelope envelope.json
```

Only synthetic or public documents go in this repo. Real documents stay out of
the repo and out of AI tools.

## Team

- **Precious:** taxonomy, quality criteria, the confidence policy and
  escalation, and benchmarks.
- **Francis:** package engineering, the work contract, and extraction.

## Documents

- [Proposal (v2)](docs/proposal.md)
- [Taxonomy Frame](taxonomy/document-taxonomy.frame.md) and [taxonomy notes](taxonomy/README.md)
- [Notes on the suite](docs/suite-notes.md)
- [Benchmark set](benchmarks/README.md): plan, labeling, targets and how to run it

## License

Our own code and documents are licensed under [Apache-2.0](LICENSE). Smith
supplied the starter templates and machinery in `src/` and `scripts/`, under
Apache-2.0; see [LICENSE.smith](LICENSE.smith), [NOTICE.smith](NOTICE.smith)
and [LICENSING.md](LICENSING.md).
