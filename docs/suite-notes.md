# Notes on the Cog / Op Builder suite

These notes collect what we learned studying the cogcloud-ai suite. They hold
the facts that shape this Cog's design. The suite is an experimental preview, so
re-check before relying on any detail.

**Checked against:** suite commit `71834ce` (pins as of 10 October 2026),
cog-smith `c700f66` (decision machinery 0.1.4, Op machinery 0.9.3), and
cog-workbench `fc9bb85`. Last re-checked on 13 October 2026.

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

`answered_by.answer_source` records which kind of model answered. The
machinery calls `decide(bundle, answers)` without it, so `decide` cannot apply a
different threshold to each provider. To treat providers differently, use
`check_output`, which sees the whole payload, or ask cog-smith to pass
`answered_by` to `decide`.

## Running local Qwen

Since 19 October 2026 the Cog runs live with local Qwen (decision 2):
cog-qwen serves Qwen3-4B (Q4_K_M) on this machine, cog-system-one-adapter asks
it the Cog's questions, and Workbench binds both and activates them for this
Cog. It needed three local changes, and a cap on thinking. The files are in
[`local-qwen/`](local-qwen/README.md).

**Three problems, and what we did**

| Problem | Effect | What we did |
|---|---|---|
| cog-qwen's Linux build of llama.cpp (`cpu_mkl`) has no AVX2 or FMA code | On an i7-8750H, Qwen wrote under 1 token a second, and every call hit the gateway's 180-second limit | Serve the same pinned, checksum-checked model with a CUDA build of the same llama.cpp version, on a GTX 1070: about 30 tokens a second (`serve.sh`) |
| The adapter asks for JSON only in the prompt | Qwen3-4B copied the whole answer schema back, then answered in the wrong shape, so every call failed | Adapter setting `enforce_schema`: the gateway enforces the answer schema, which cog-qwen already supports as `json-schema` |
| cog-qwen always turns Qwen3's thinking off | 10.6% silent errors on the benchmark without thinking, 5.3% with it | cog-qwen setting `enable_thinking`, set by the binding, never by a caller |

The adapter answers at temperature 0, and at temperature 0 Qwen's thinking
sometimes loops until the output limit, so the call fails. `serve.sh` caps
thinking at 3,000 tokens (llama.cpp `--reasoning-budget`) and then makes Qwen
answer. Normal thinking stayed under 2,400 tokens. Qwen's recommended sampling
for thinking (temperature 0.6, top-p 0.95, top-k 20) also stops the loops, but
it made borderline answers random enough to turn a caught mistake into a silent
one.

The three problems are worth raising with the suite team.

**Setup**, in the suite workspace:

1. cog-qwen: `pixi install`, `pixi run fetch`, and the two tokens from its
   README in `COG_QWEN_BACKEND_TOKEN` and `COG_QWEN_TOKEN`. Apply
   `cog-qwen-enable-thinking.diff`.
2. `llama-cuda/`: copy `pixi.toml`, `serve.sh` and `restart.sh` there, run
   `pixi install`, then `./restart.sh` to start the model server.
3. cog-qwen: start the gateway with
   `pixi run serve -- --state-dir ../cog-workbench/var/suite/qwen --port 8114`.
4. cog-system-one-adapter: apply `cog-system-one-adapter-enforce-schema.diff`
   and run `pixi install`.
5. cog-workbench: bind `qwen-local-3.json` with `--provider cog-qwen`, then
   `system-one-qwen-3.json` with `--provider cog-system-one-adapter`, using
   absolute paths, since pixi runs from cog-workbench. Then activate revision 3
   for this Cog (see Useful commands).
6. Here, with the tokens set: `pixi run ask-composed -- --request examples/sample-bundle.json`.

Keep the model server and the gateway running in the background, detached
from the terminal. A document takes 30 to 40 seconds on the GTX 1070, and a
benchmark run about 50 minutes. If the GPU drops to a low-power state, for
example on battery, or other programs load the CPU, Qwen slows to 6 to 20
tokens a second, and long thoughts hit the gateway's 180-second limit.

**Context.** The fixed part of the prompt, with 20 questions, is about 2,900
tokens. Thinking takes up to about 2,400 tokens (3,000 at the cap) and the
answer about 300. To leave room for a capped thought within 8,192 tokens, the
text must stay under about 2,000 tokens: roughly 6,000 to 8,000 characters.
That is the limit for decision 4 (#2) while thinking is on, unless the context
grows to 16,384 tokens, which the GPU can hold but cog-qwen fixes at 8,192.

**What we learned about Qwen3-4B**

- **Answers vary between runs,** even at temperature 0: a restarted server is
  enough to flip a borderline document. Judge changes on more than one run.
- **It reads exclusions in an option's description and still overrides
  them.** Clearer wording fixed none of five targeted mistakes. A rule holds
  only when a simple question feeds `decide`, which applies it in code.
- **One fact per question.** It answered half of a two-part question and
  ignored the rest. Multiple choice worked better than yes/no for "who issued
  this?". The question's ID is part of the prompt, and "provider" in
  `issued_by_account_provider` misled it.
- **Answers in one call aren't independent.** Once it has decided on a type,
  its other answers tend to agree with that type, so the `issuer` question
  catches about half of its bank statement mistakes.
- **Its confidence is almost always 1.0 or 0.0,** so no threshold helps, and
  the `calibrated-answers` Guard warns on every result.
- **With several documents in one file,** the type question's "classify the
  main one" makes it pick a main document, usually the first page, so the
  `main_document_clear` question rarely fires.

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
probability. With our six types, a confidence of 0.85 means a top probability of
0.875.

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
- **Guards can't run in Ops yet:** `gate.guards` must be `[]`. Until the Hub
  runs Guards, this Cog's Guards run as scripts in `guards/` and in CI. They're
  defined in the Frame, which Travis described as where Guards and their
  failure behaviour belong.

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

From cog-workbench, after `pixi install`, to check that Workbench sees this Cog
and which providers fit it:

```bash
pixi run suite -- catalog
echo '{"capability": "system-one/decisions", "accepted_compositions": ["model+harness", "harness"]}' > /tmp/requirement.json
pixi run suite -- select --requirement /tmp/requirement.json
```

On 13 October 2026, `select` matched two providers:
- cog-typesafe (`model+harness`);
- cog-system-one-adapter (`harness`).

Both example bindings offer the `choice`, `noul` and `score` question types,
which covers the `choice` and `noul` this Cog uses.

The benchmark set, from this package. See `benchmarks/README.md`:

```bash
pixi run python benchmarks/bench.py                                  # check the labels
pixi run python benchmarks/run.py live --name NAME                   # once a provider is active
pixi run python benchmarks/score.py benchmarks/results/NAME --split tune
```

Live, after admitting a provider in cog-workbench. For local Qwen (see
[Running local Qwen](#running-local-qwen)), the binding is
`binding-system-one-qwen`, revision 3:

```bash
# in cog-workbench
pixi run suite -- activate-composition --context cog-document-classification --binding-id ID --revision N
# in this package
pixi run ask-composed -- --request bundle.json
```

Activate again after any change to `pixi.toml`, `src/`, `scripts/` or
`context/`: Workbench refuses a call when this package's fingerprint has
changed.
