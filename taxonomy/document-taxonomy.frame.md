---
type: frame [0.2]
name: Document Type Taxonomy
description: Defines the standard document types, boundary rules and tag vocabulary for classifying one incoming business document by its purpose. Use it whenever a document must get exactly one type and tags from a fixed list, or go to review when that cannot be done reliably.
visibility: internal
version: 0.1.0
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
- Not the filename. Filenames are often generic or wrong, and can contain personal data. *(Working assumption; confirm.)*

## Terminology

- **`invoice`**: a request for payment from a seller to a buyer for goods or services, stating what is owed. Includes tax and VAT invoices, utility and subscription bills, and payment reminders or overdue notices for an invoice.
- **`contract`**: an agreement that sets out obligations between two or more named parties, signed or meant to be signed. Includes service and supply agreements, statements of work, non-disclosure agreements, employment contracts, leases, licences, and amendments or renewals of an agreement.
- **`resume`**: a person's own summary of their work history, education and skills, written to apply for jobs. Also called a CV. The ID is always ASCII `resume`; "Résumé" is only a display label.
- **`support_ticket`**: a request for help, or a report of a problem, sent by a customer or user to the team behind a product or service. Includes helpdesk tickets, support emails, bug reports, complaints, access requests and billing disputes raised with support.
- **`other`**: any document that is not one of the four types above. It is a real type, not a holding place for uncertainty.
- **Tag**: a yes/no label from the vocabulary below. General tags can apply to any type. Type tags are reported only with their own type.
- **Review**: the outcome when no type can be assigned reliably. It carries no type, and it states its reasons.

## Tag Vocabulary

General tags:

| Tag | Applies when |
|---|---|
| `contains_personal_data` | An identifiable person is named together with personal details such as contact details, home address, date of birth or an ID number |
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
| `invoice_credit_note` | `invoice` | It credits or refunds money rather than charging it |
| `contract_nda` | `contract` | It is a non-disclosure or confidentiality agreement |
| `contract_employment` | `contract` | It is an employment contract or sets employment terms |
| `contract_amendment` | `contract` | It amends, renews or extends an existing agreement |
| `ticket_urgent` | `support_ticket` | It reports something blocking, an outage or money being lost now, or states urgency |
| `ticket_complaint` | `support_ticket` | It expresses dissatisfaction, or asks for escalation or compensation |
| `ticket_billing` | `support_ticket` | It is about billing, payments, charges or refunds |
| `ticket_bug_report` | `support_ticket` | It reports a defect or error in a product or service |

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

Working assumptions for borderline cases *(confirm before relying on them)*:
- Pro-forma invoices are `invoice`: they request payment, even in advance.
- Credit notes are `invoice`, tagged `invoice_credit_note`.
- Receipts, payment confirmations and account statements are `other`.
- Offer letters are `contract`, tagged `contract_employment`.
- Unsigned contract templates are `contract`, tagged `draft_or_template`.
- Published website terms of use are `other`.
- Cover letters on their own are `other`.
- Profile pages exported from professional networks are `resume`.
- Sales enquiries asking for a quote are `other`: they ask to buy, not for help.
- A support team's reply without the customer's request is a `support_ticket`.

More than one document:
- If the text holds several documents, classify the main one and apply `multiple_documents`.
- If no document is clearly the main one, send it to review.

Signals (evidence, never the decision on their own):
- `invoice`: an invoice number and date, amount or balance due, a due date, "bill to" or "remit to", priced line items, tax lines, payment terms, bank or payment details.
- `contract`: "Agreement", named Parties, recitals ("Whereas"), a definitions section, numbered clauses, term and termination, governing law, signature blocks.
- `resume`: Experience, Education and Skills sections; a person's name and contact details at the top; dated roles with employers; "Curriculum Vitae".
- `support_ticket`: a ticket number, a subject line, status or priority fields, a user describing a problem, steps to reproduce, a refund request.

Tagging:
- Apply a tag only when its statement clearly holds. Leave it off when unsure.
- Report a type tag only when the document has that type.
- Contradictions go to review *(working assumption; confirm)*:
  - a type tag clearly holds for a different type than the one chosen;
  - an `invoice` states no monetary amounts.

Review:
- When the type is unclear, send the document to review. Never fall back to `other`.
- When the text is mostly garbled, fragmentary or empty, send it to review and say so.
- Every review outcome states its reasons.

Language:
- The definitions apply in any language. Apply `non_english` when the main language is not English.

## Style

- Write type and tag IDs exactly as listed: lowercase ASCII with underscores.
- Write review reasons as plain statements of the evidence, for example "type confidence is below the threshold" or "text is mostly OCR noise".

## Do Not

- Do not infer age, gender, ethnicity, religion, health, disability or any other protected characteristic from any document.
- Do not use `other` for a document you are unsure about.
- Do not decide a type from a keyword alone.
- Do not assign more than one type.
- Do not apply a tag outside the vocabulary, or invent a new one.
