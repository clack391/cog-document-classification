# Notes on the Cog / Op Builder suite

These notes collect what we learned studying the cogcloud-ai suite. They hold
the facts that shape this Cog's design. The suite is an experimental preview, so
re-check before relying on any detail.

**Checked against:** suite commit `71834ce` (pins as of 10 October 2026),
cog-smith `c700f66` (decision machinery 0.1.4), and cog-workbench `fc9bb85`.

## The suite in brief

- **Cog:** a packaged AI worker.
  - It consists of `COG.md` (the human contract), a manifest (`[tool.cog]` in
    `pixi.toml`) and JSON schemas in `context/`.
  - Every run returns envelope v1:
    `{envelope, cog, task, ok, error, payload, raw, problems, binding, timing}`.
    `ok: true` can still carry problems.
- **Decision Cog:** a context Cog whose model answers typed questions while the
  Cog's own code decides. That is this Cog.
- **cog-smith:** creates and checks Cogs. Everything in `src/` except
  `task_logic.py` is shared machinery checked by hash. Never edit it here.
  Helper modules of our own are allowed.
- **cog-workbench:** the local host. It admits model providers and composes them
  with Cogs. A decision Cog never picks its own model.
- **Op:** a workflow (`op.yaml`) that runs Cogs as steps behind Gates and keeps a
  durable run record, the Track.
- **The automated builder** (op-cog-builder) builds pure-code Cogs only, so this
  Cog is built by hand from Smith's decision template.

Key reading in the suite:
- `cog-smith/BUILDING_COGS.md` §7c on decision Cogs;
- `cog-smith/BUILDING_OPS.md` on Gates and the human Gate;
- `cog-op-builder/docs/system-one-decisions.md`;
- `cog-brief-router`, the worked example.

## What we own in this package

- **`context/questions.json`:** the typed questions.
  - `noul`: a probability that a statement is true.
  - `choice`: 2–255 options, each with a probability, plus a confidence.
  - `score`: 2–10 ordered levels.
- **`context/input-schema.json`** and **`$defs.decision`** in
  `context/output-schema.json`. `$defs.answers` is derived from the questions by
  `pixi run derive-schema`.
- **`src/task_logic.py`:**
  - `check_input`;
  - `state` (what the model sees);
  - `questions` (may change wording only);
  - `decide`;
  - `check_output`.
- **The rest:** `COG.md`, the manifest, `examples/` and `tests/`.

The payload is always `{decision, answers, answered_by}`. Our fields go inside
`decision`.

## Model providers

| Provider | Model | Data | Confidence |
|---|---|---|---|
| cog-typesafe | TypeSafe's Jev, a versioned ID such as `jev-1.13.0` | Cloud: the state and questions go to TypeSafe. Input tokens are billed. Needs `TYPESAFE_API_KEY`. | Trained for calibration. The suite publishes no accuracy figures. |
| cog-system-one-adapter | A local cog-qwen or cog-openrouter model | cog-qwen keeps data on the machine. | Stated by an LLM, so not calibrated. |

`answered_by.answer_source` records which kind of model answered.

## Limits that shape the design

**Model input**

- **At most 64 questions per document.** One type question leaves room for up to
  63 tags.
- **At most 512 KiB of state per call,** and the state must not be empty.
- **Local Qwen's context is 8,192 tokens,** shared by the prompt, the questions
  and the answer.
- **The models read text only,** so extraction and OCR run in our code.

**Time limits**

- **240 seconds for each of our two bridge phases,** run as separate processes:
  - `prepare` runs `check_input` and `state`;
  - `finish` runs `check_input`, `decide` and `check_output`.
- **The model turn has its own limit:** 660 seconds on the Workbench side.
- **`decide` never sees what `state` extracted.** It must recompute any
  extraction signal or read it from a cache.

**Runtime environment**

- **The Workbench fingerprint** covers `pixi.toml`, `src/`, `scripts/` and
  `context/`, among others. Changing them requires re-activation, and a change
  during a call fails the call. Caches belong outside those folders.
- **The Cog runs in its own Pixi environment,** so extraction libraries go in
  `pixi.toml`.
- **Bridge output must be pure JSON on stdout.**
- **Nothing is sandboxed.** Untrusted files are parsed with the permissions of
  whoever runs the Cog.

**Extraction libraries**

These are on conda-forge for both platforms the suite supports:
- pypdf (BSD);
- pdfplumber (MIT);
- pypdfium2 (Apache);
- tesseract and pytesseract (Apache);
- python-docx (MIT).

Avoid PyMuPDF: its license is AGPL.

**Confidence**

A choice answer's `confidence` is `(p_top − 1/n) / (1 − 1/n)`, not the top
probability. With five types, a confidence of 0.85 means a top probability of
0.88.

## Input checks and review

- **`check_input` severities:** severity `error` refuses the run; severity
  `warning` lets it proceed and is carried into `problems`.
- **The Op Gate policy:** `envelope-ok-no-error-problems` fails a step on
  `ok: false` or on any error problem. Warnings give `pass-with-problems`.
- **What a Gate reads:** only `ok`, `error` and `problems`, never payload
  fields.
  - So `needs_review` must also be reported as a **warning** problem.
  - The `cog_core.problem()` helper defaults to `error`.
- **Human Gates pause on every run.** Op steps have no conditions, so an Op
  cannot pause only for uncertain documents.
- **Guards can't run in Ops yet:** `gate.guards` must be `[]`.

## Useful commands

From this package:

```bash
pixi install
pixi run test
pixi run check
pixi run prepare -- --bundle examples/sample-bundle.json
pixi run replay -- --bundle examples/sample-bundle.json --result examples/sample-result.json
pixi run derive-schema
```

From cog-smith:

```bash
pixi run check -- ../cog-document-classification --tests
pixi run card -- ../cog-document-classification
```

Live, after admitting a provider in cog-workbench:

```bash
# in cog-workbench
pixi run suite -- activate-composition --context cog-document-classification --binding-id ID --revision N
# in this package
pixi run ask-composed -- --request bundle.json
```
