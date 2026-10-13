**Project Proposal & Execution Blueprint: Document Classification Cog (v2 draft)**

**Lead Contributors:** Precious & Francis
**Stakeholders:** Trent & Inessa
**Built on:** the cogcloud-ai Cog / Op Builder suite, as a decision Cog (cog-smith's `decision` class)
**Repository:** https://github.com/clack391/cog-document-classification
**Target Output:** A portable, read-only Cog. It identifies a document's type, assigns tags from a fixed vocabulary and reports the model's confidence. It flags uncertain or unreadable documents for review.

Items marked **[TBD: decision N]** depend on the open decisions in section 5.

**1. Project Mission & Objective**

The Document Classification Cog serves as the "front door" for incoming documents. Before specialized Cogs can process an invoice, route a ticket, or evaluate a candidate, the system must first establish what the document is.

* **Primary Function:** Take one document file and extract its text in our own code. Run OCR for scanned pages. Then ask a System One model a fixed set of typed questions about the text. Supported formats are PDF, scanned images and text-based files; the exact list and the maximum length are **[TBD: decision 4]**. Email attachments reach the Cog as files from whatever system receives the email. From the model's answers, the Cog:
   * assigns one document type: `invoice`, `contract`, `resume` (résumé), `support_ticket` or `other`;
   * assigns tags from a fixed vocabulary of 16 tags;
   * reports the model's confidence in the type;
   * records file and extraction metadata: file type, page count, size, sha256, whether OCR was used **[TBD: decision 3]**;
   * marks any document it cannot classify reliably as `needs_review`, with reasons.
* **How It Works:**
   * The model answers narrow questions with probabilities. The Cog's own code turns those answers into the classification and applies our thresholds.
   * The suite's local host (cog-workbench) and a model provider connect the model. The Cog never chooses its own model. The provider is **[TBD: decision 2]**.
* **System Impact:**
   * The Cog is read-only: it never writes, sends or modifies anything outside its own result, and it declares these prohibitions in its manifest.
   * Downstream workflows get a classification they can route on. Each result carries the model, its answers and the confidence, and from Phase 2 the document's sha256, so anyone can audit it.

**2. Guardrails & Governance Standards**

To ensure accountability and prevent misclassification:

* **Zero-Guessing Policy:** The Cog never assigns a type it is not confident in.
   * When the confidence is below the threshold, or extraction was poor, the result is `needs_review` with stated reasons and no document type.
   * `other` is a real type for documents outside the taxonomy, not a fallback for uncertainty.
* **Confidence Policy:** The model returns a confidence with its answer about the type. The Cog compares it with a threshold in its decision code, where the policy is readable and covered by tests.
   * The starting threshold is 0.85, to be tuned on the benchmark sets.
   * This confidence is not the top probability. With five types, a confidence of 0.85 means a top-type probability of 0.88.
   * Jev's confidence is trained for calibration; a local LLM's is not.
   * Limitation: the suite does not yet tell the decision code which model answered, so one set of thresholds applies to every model for now. The taxonomy notes list the ways around this.
* **Escalation:**
   * Unclear documents are marked `needs_review` and reported as a warning in the result, so any workflow or consumer sees them. This covers a confidence below the threshold, poor or partial text extraction, and answers that contradict each other.
   * Documents with no extractable text are refused with a clear input error.
   * Whoever consumes the result routes `needs_review` documents to a person. Whether we also ship an Op with a human approval Gate is **[TBD: decision 6]**.
* **Accountability:** Every result records:
   * which model answered, and whether it was Jev or an LLM;
   * every typed answer;
   * the document's sha256, from Phase 2.

   So any classification can be traced and replayed.
* **Terminology:** We use the suite's terms:
   * **contract checks** are the Cog's checks of its own output;
   * **Guards** are independent checkers run by the wider system;
   * **Gates** decide whether a workflow continues.

**3. Role Breakdown & Technical Ownership**

**Precious: Lead for Taxonomy, Quality Criteria & Accountability**

* **Taxonomy Frame:** Author `document-taxonomy.frame.md` (Frame Spec v0.2), establishing category definitions, keyword associations, and tagging rules, as the human reference. Encode it in `context/questions.json`, which is what the model sees:
   * the type question's option descriptions;
   * one yes/no question per tag, up to 63 tags.

   Keyword hints go into the option descriptions.
* **Confidence Policy:** Define the thresholds, the escalation triggers, and the reasons the Cog reports. They live in `decide` in `src/task_logic.py`.
* **Escalation Protocol:** Define how `needs_review` results reach a person: who reviews them, what they see, and how their decision is recorded.
* **Quality Assurance:** Assemble benchmark sets: invoices, contracts, résumés, support tickets and other documents, plus edge cases such as scans, mixed documents and near-empty files.
   * Measure accuracy and calibration for each model, and tune the thresholds.
   * Save real model answers as replay tests, so the policy stays tested without calling a model.
* **Stakeholder Alignment:** Lead project updates with Trent, Inessa, and the broader team, including decisions 2, 3 and 6.

**Francis: Lead for Package Engineering, Extraction & Work Contract**

* **Specification & Contract:** Author `COG.md`, the human-readable contract, and the schemas in `context/`:
   * `input-schema.json`, the input bundle.
   * `output-schema.json`. Our fields (`document_id`, `status`, `document_type`, `confidence`, `tags`, `flags`, `reasons`, and metadata once decision 3 is settled) go in its `decision` section.
* **Package Manifest:** Maintain the `[tool.cog]` table in `pixi.toml`, the file Nebi publishes.
   * Include the extraction dependencies (for example pypdf, pypdfium2 and tesseract) and the declared prohibitions.
   * Commit `pixi.lock`. It pins exact versions for Linux x86-64 and Apple Silicon.
* **Extraction & Model Hookup:**
   * Build the extraction module: text, OCR, and trimming the text to the model's limits.
   * Connect the model by admitting a provider in cog-workbench (Jev through cog-typesafe, or local Qwen through cog-system-one-adapter) and activating it for the Cog. No custom harness or model binding is needed.
* **Build & Assembly:**
   * Create the Cog with cog-smith. *(Done 12 Oct 2026.)*
   * Run it offline with `prepare` and `replay`, and live with `ask-composed`.
   * Validate throughout by running `pixi run check -- ../cog-document-classification --tests` from cog-smith.

**4. Implementation Phasing**

```
[ Phase 1: Contract & Questions ] ➔ [ Phase 2: Extraction & Provider ] ➔ [ Phase 3: Decision Policy & Review ] ➔ [ Phase 4: Benchmarks & Handoff ]
```

* **Phase 1: Setup, Contract & Questions** *(in progress)*
   * Create the Cog with `smith new --class decision`. *(Done 12 Oct 2026.)*
   * Draft `document-taxonomy.frame.md` and encode it in `questions.json`. *(Done 12 Oct 2026: the working assumptions and 16 tags are confirmed, and the questions are in `context/questions.json`.)*
   * Write `COG.md` and the input and output schemas. *(Provisional schemas are in place: text input, and no metadata fields yet. The final versions wait on decisions 4 and 3. `COG.md` is not started.)*
   * Smith validation passes from this phase onward. *(It passes, and CI runs it on Linux and macOS for every push.)*
* **Phase 2: Extraction & Provider**
   * Add the extraction dependencies to `pixi.toml` and commit `pixi.lock`.
   * Build the extraction module. Its limits:
      * up to 512 KiB of text per document, and about 8,000 tokens for local Qwen;
      * 240 seconds for each stage of our code.
   * Settle decision 2, then set up the provider in cog-workbench.
* **Phase 3: Decision Policy & Review** *(started early)*
   * Implement the confidence policy and escalation triggers in the decision code. *(First version done 12 Oct 2026. The thresholds are placeholders until Phase 4.)*
   * Report `needs_review` as a warning, and refuse documents with no extractable text. *(Done 12 Oct 2026.)*
   * Settle decision 6, then implement the agreed review path.
* **Phase 4: Benchmarks, Validation & Handoff**
   * Run the benchmark sets live, measure accuracy and calibration, and tune the thresholds.
   * Save real answers as replay tests.
   * Run the final validation with cog-smith (`check --tests` and `card`).
   * Publish integration notes so downstream Cogs can consume the `decision` schema.

**5. Open Decisions**

1. **Which cog-smith version:** *settled 12 Oct 2026.* The suite's pins moved on 10 October to include the newer cog-smith, with input warnings and test-fixture export (decision machinery 0.1.4). We build on the suite's current pins.
2. **Cloud Jev or local Qwen:** Jev sends the extracted text to TypeSafe. Contracts and résumés hold personal data. Owners: Trent & Inessa. Needed before Phase 2.
3. **What "metadata" covers:** file and extraction facts only, or content fields such as invoice numbers. Content fields would need a second Cog. Owners: the team with Trent & Inessa. Needed before the output schema is fixed.
4. **How documents arrive:** a file path with its sha256 recorded, or the file embedded in the input; plus the supported formats and maximum length. Owner: Francis. Needed before the input schema is fixed.
5. **Tag vocabulary:** *settled 12 Oct 2026.* 16 tags, confirmed by Precious, are listed in the taxonomy Frame.
6. **What review looks like:** consumers routing on `needs_review`, or an Op with a human approval Gate on every document. Owners: Trent & Inessa. Needed before Phase 3.

**6. What Changed from v1**

* **The `résumé` type ID:** it becomes ASCII `resume`. "Résumé" stays as the label.
* **"Compute a classification confidence score":** the Cog now reports the model's confidence and applies a threshold.
* **Confidence Guard:** it becomes the Confidence Policy, because in the suite a "Guard" is an independent checker outside the Cog.
* **Human Approval Gate, "immediately diverted":** the Cog now sets a `needs_review` flag and reports a warning, and the consumer routes on it. The suite's human Gate pauses every run and cannot route selectively. An Op with a human Gate is decision 6.
* **`cog.md` with the schemas inside:** it becomes `COG.md`, with the schemas in `context/*.json` and the questions in `questions.json`.
* **Harness development and model binding:** this becomes an extraction module plus provider setup. The suite's host connects the model.
* **"Pinned Nebi environment dependencies":** pinning comes from `pixi.lock`.
* **"Read-only permissions to guarantee zero operational risk":** the Cog now "never writes, sends or modifies anything". The suite does not sandbox Cogs, so "zero risk" overstated it.
* **Metadata:** it is scoped to file and extraction facts until decision 3.
* **Phasing:** creating the Cog and validating it with Smith now start in Phase 1, and the choice of model provider is a named step in Phase 2.
