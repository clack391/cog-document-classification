# cog-document-classification

A Cog that classifies one incoming business document, built on the
[cogcloud-ai Cog / Op Builder suite](https://github.com/cogcloud-ai/cog-op-builder).

It extracts the document's text, using OCR for scans. A System One model
answers a fixed set of typed questions about that text. The Cog's own code then
assigns one type (`invoice`, `contract`, `resume`, `support_ticket` or
`other`), adds tags from a fixed vocabulary, and reports the model's confidence.
Any document it cannot classify reliably is marked `needs_review`, with reasons.

It is a **decision Cog**, created with cog-smith's decision template
(`smith new --class decision`). The model answers narrow questions; the policy
(thresholds, tags, escalation) is plain code in `src/task_logic.py` that we can
read and test.

## Status

Phase 1, in progress. The package passes Smith's checks and its offline tests
on the suite's current pins.

**What works**
- The confirmed taxonomy: the [Frame](taxonomy/document-taxonomy.frame.md) and
  the 18 questions in `context/questions.json` built from it.
- A first decision policy in `src/task_logic.py`: the type at confidence 0.85
  or above, tags at 0.7, and review for low confidence, illegible text or
  contradicting answers.
- Tests that keep the Frame, the questions, the policy and the output schema in
  agreement.

**What is provisional**
- The input is the document's extracted text. File input and extraction come
  in Phase 2, and the final input format is decision 4.
- The output schema has no metadata fields yet. That waits on decision 3.
- The thresholds are placeholders until the benchmark sets tune them.

**What is not started**
- `COG.md` still has the starter's placeholder sections.

See the [proposal](docs/proposal.md) for the plan, the phases and the open
decisions.

## Layout

| Path | What it is | Owner |
|---|---|---|
| `COG.md` | The human-readable contract | Francis |
| `pixi.toml` | Environment and the `[tool.cog]` manifest | Francis |
| `pixi.lock` | Exact pinned dependencies for Linux x86-64 and Apple Silicon | Francis |
| `context/` | Input schema, output schema and the questions the model answers | Francis, with Precious for the questions |
| `src/task_logic.py` | Extraction hookup and the decision policy. Every other file in `src/` is Smith machinery; never edit it. | Francis, with Precious for the policy |
| `taxonomy/` | The taxonomy Frame (the source of truth) and its notes | Precious |
| `tests/` | Offline tests. They need no model. | Both |
| `docs/` | The proposal and notes on the suite | Both |

## Getting started

You need Git, Python 3.11 or newer, and [Pixi](https://pixi.sh). This Cog must
sit next to the suite's components in one workspace folder, because its live
entry point looks for `../cog-workbench`.

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
pixi install
pixi run check -- ../cog-document-classification --tests
```

Working without a model:

```bash
pixi run prepare -- --bundle examples/sample-bundle.json
pixi run replay -- --bundle examples/sample-bundle.json --result examples/sample-result.json
```

`prepare` shows what would be sent to the model. `replay` decides from saved
answers.

Live runs need a model provider admitted in cog-workbench: TypeSafe's Jev in the
cloud, or local Qwen through the System One adapter. Which one we use is still
open; see the proposal.

## Team

- **Precious:** taxonomy, quality criteria, the confidence policy and
  escalation, and benchmarks.
- **Francis:** package engineering, the work contract, and extraction.

## Documents

- [Proposal (v2)](docs/proposal.md)
- [Taxonomy Frame](taxonomy/document-taxonomy.frame.md) and [taxonomy notes](taxonomy/README.md)
- [Notes on the suite](docs/suite-notes.md)

## License

Our own code and documents are licensed under [Apache-2.0](LICENSE). Smith
supplied the starter templates and machinery in `src/` and `scripts/`, under
Apache-2.0; see [LICENSE.smith](LICENSE.smith), [NOTICE.smith](NOTICE.smith)
and [LICENSING.md](LICENSING.md).
