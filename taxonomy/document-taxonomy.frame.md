---
type: frame [0.2]
name: Document Type Taxonomy
description: Defines the standard document types, boundary rules and tag vocabulary for classifying one incoming business document by its purpose. Use it whenever a document must get exactly one type and tags from a fixed list, or go to review when that cannot be done reliably.
visibility: internal
version: 0.4.2
scope: task-family
maintainer: Document Classification Cog team
---

# Document Type Taxonomy

## Goals

- Give every document exactly one type from a fixed list, based on what the document is for.
- Apply tags only from the fixed vocabulary, and only when they clearly hold.
- Send a document to review instead of guessing whenever its type is unclear or its text is unreadable.
- Keep types and tags stable so downstream workflows can route on them.

## Inputs

- The extracted text of one document. Scanned pages arrive as OCR text and may contain recognition errors.
- Not the filename. Filenames are often generic or wrong, and can contain personal data.

## Terminology

- **`invoice`**: a request for payment from a seller to a buyer for goods or services, stating what is owed. Includes tax and VAT invoices, pro-forma invoices, credit notes, utility and subscription bills, and payment reminders or overdue notices for an invoice.
- **`contract`**: an agreement that sets out obligations between two or more named parties, signed or meant to be signed. Includes service and supply agreements, statements of work, non-disclosure agreements, employment contracts, job offer letters, leases, licences, amendments or renewals of an agreement, and unsigned contract templates.
- **`resume`**: a person's own summary of their work history, education and skills, written to apply for jobs. Also called a CV. Includes profiles exported from professional networking sites. The ID is always ASCII `resume`; "Résumé" is only a display label.
- **`support_ticket`**: a request for help, or a report of a problem, sent by a customer or user to the team behind a product or service. Includes helpdesk tickets, support emails, bug reports, complaints, access requests, billing disputes raised with support, and the support team's replies within a ticket.
- **`bank_statement`**: a statement or transaction history for a bank, credit card or payment account, issued by the bank, card issuer or payment provider: the account holder, the account, a period, opening and closing balances, and dated transactions. Includes bank and credit card statements, and transaction-history exports from online banking or payment providers.
- **`other`**: any document that is not one of the five types above. It is a real type, not a holding place for uncertainty.
- **Tag**: a yes/no label from the vocabulary below. General tags can apply to any type. Type tags are reported only with their own type.
- **Review**: the outcome when no type can be assigned reliably. It carries no type, and it states its reasons.

## Tag Vocabulary

General tags:

| Tag | Applies when |
|---|---|
| `contains_personal_data` | An identifiable person is named together with personal details such as contact details (work or personal), home address, date of birth or an ID number |
| `contains_financial_amounts` | Specific monetary amounts are stated |
| `time_sensitive` | A deadline, due date or required response time is stated |
| `signed` | There is evidence of completed signatures: filled signature blocks, "signed by", dated signatures, an e-signature certificate |
| `draft_or_template` | The document is marked draft, template, sample or specimen, or has unfilled placeholders such as `[NAME]` |
| `multiple_documents` | The file contains more than one distinct document |
| `non_english` | The main language is not English |

Type tags:

| Tag | Type | Applies when |
|---|---|---|
| `invoice_reminder` | `invoice` | It is a payment reminder, overdue notice or final notice |
| `invoice_credit_note` | `invoice` | It is a credit note: it credits or refunds money rather than charging it |
| `contract_nda` | `contract` | It is a non-disclosure or confidentiality agreement |
| `contract_employment` | `contract` | It is an employment contract or a job offer letter that sets employment terms |
| `contract_amendment` | `contract` | It is an agreement that amends, renews or extends an earlier agreement |
| `ticket_urgent` | `support_ticket` | It is a support request reporting something blocking, an outage or money being lost now, or stating urgency |
| `ticket_complaint` | `support_ticket` | It is a complaint: it expresses dissatisfaction, or asks for escalation or compensation |
| `ticket_billing` | `support_ticket` | It is a support request about billing, payments, charges or refunds |
| `ticket_bug_report` | `support_ticket` | It is a support request reporting a defect or error in a product or service |

## Rules

**Classify by purpose, not by topic.** Ask what the document is for, not what it mentions. Every boundary case below follows from this.

Type boundaries:
- A complaint or question about a bill is a `support_ticket`, not an `invoice`.
- An invoice issued under a contract is an `invoice`.
- A letter or email that discusses a contract is classified by its own purpose, usually `other` or `support_ticket`.
- Quotes, estimates and purchase orders are `other`: nothing is owed yet, or the buyer is the one placing the order.
- Proposals not yet agreed, company policies and handbooks are `other`.
- Job descriptions, job adverts, reference letters and performance reviews are `other`.
- Internal incident reports, post-mortems and feedback surveys are `other`.

Borderline cases (confirmed 12 October 2026):
- Pro-forma invoices are `invoice`: they request payment, even in advance.
- Credit notes are `invoice`, tagged `invoice_credit_note`.
- Receipts and payment confirmations are `other`: each records one payment, not an account's history.
- Offer letters are `contract`, tagged `contract_employment`.
- Unsigned contract templates are `contract`, tagged `draft_or_template`.
- Published website terms of use are `other`.
- Cover letters on their own are `other`.
- Profile pages exported from professional networks are `resume`.
- Sales enquiries asking for a quote are `other`: they ask to buy, not for help.
- A support team's reply without the customer's request is a `support_ticket`.

Bank statements (added 13 October 2026):
- Bank and credit card statements, and transaction-history exports, are `bank_statement`.
- A complaint or question about a bank transaction is a `support_ticket`.

Confirmed 13 October 2026:
- A supplier's statement of account, listing invoices owed to that supplier, is `other`.
- Investment, pension and loan statements are `other`.
- Payslips are `other`.

More than one document:
- If the text holds several documents, classify the main one and apply `multiple_documents`.
- If no document is clearly the main one, send it to review.

Signals (evidence, never the decision on their own):
- `invoice`: an invoice number and date, amount or balance due, a due date, "bill to" or "remit to", priced line items, tax lines, payment terms, bank or payment details.
- `contract`: "Agreement", named Parties, recitals ("Whereas"), a definitions section, numbered clauses, term and termination, governing law, signature blocks.
- `resume`: Experience, Education and Skills sections; a person's name and contact details at the top; dated roles with employers; "Curriculum Vitae".
- `support_ticket`: a ticket number, a subject line, status or priority fields, a user describing a problem, steps to reproduce, a refund request.
- `bank_statement`: a statement period, opening and closing balances, an account number, sort code or IBAN, and a table of dated transactions with debit, credit and balance columns.

Tagging:
- Apply a tag only when its statement clearly holds. Leave it off when unsure.
- Report a type tag only when the document has that type.
- Type tags describe a document of their own type, so a strong type tag for another type is a contradiction.
- Contradictions go to review:
  - a type tag clearly holds for a different type than the one chosen;
  - an `invoice` states no monetary amounts.

Review:
- When the type is unclear, send the document to review. Never fall back to `other`.
- When the text is mostly garbled, fragmentary or empty, send it to review and say so.
- Every review outcome states its reasons.

Language:
- The definitions apply in any language. Apply `non_english` when the main language is not English.

## Guards

Guards are checks on every classification result. They run independently of the system that produced the result, using this Frame as their reference. Each guard states what happens when it fails.

| Guard | Passes when | On failure |
|---|---|---|
| `no-document-text` | The result repeats no passage of the document: no run of 30 or more characters of its text | Fail: block the result and send the document to a person |
| `no-personal-identifiers` | The result contains no email addresses, phone numbers, payment card numbers, IBANs or US Social Security numbers | Fail: block the result and send the document to a person |
| `known-vocabulary` | The type is one of this Frame's types, every tag is in the vocabulary, type tags appear only with their own type, and a result in review has no type and at least one reason | Fail: block the result and send the document to a person |
| `review-is-visible` | A result in review is also reported as a warning, so no workflow can pass it as clean | Fail: block the result and send the document to a person |
| `calibrated-answers` | The answers came from a System One model trained for calibration, not from an LLM asked for probabilities | Warn: keep the result, and note that its confidence is not calibrated |

A failed guard is never repaired automatically. The result is held back, and the reason is recorded.

Guards check what the system produced. The caller's own document identifier is echoed back in the result unchanged, so it is not checked, as long as it matches the identifier in the input.

## Style

- Write type and tag IDs exactly as listed: lowercase ASCII with underscores.
- Write review reasons as plain statements of the evidence, for example "type confidence is below the threshold" or "text is mostly OCR noise".

## Do Not

- Do not infer age, gender, ethnicity, religion, health, disability or any other protected characteristic from any document.
- Do not use `other` for a document you are unsure about.
- Do not decide a type from a keyword alone.
- Do not assign more than one type.
- Do not apply a tag outside the vocabulary, or invent a new one.
