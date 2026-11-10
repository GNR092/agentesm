---
disabled: true
---

# Task prompts: one input, one output

**Source:** [https://systempromptmaster.com/learning/task-prompts](https://systempromptmaster.com/learning/task-prompts)
**Downloaded:** 2026-11-10

**Description:** How to write a prompt that does one thing: input and output described field by field, a declared value when the input cannot answer, and cases to test.

> **Quick answer:** Describe the input field by field, describe the output field by field, declare a value for input that cannot produce an answer, choose a batch or one call per item by what an error costs, and test the prompt against a list of cases with expected outputs.

A task prompt does one thing: material goes in, a result comes out, and nothing carries over from one call to the next. There is no persona to sustain, no conversation to remember, no tool to call.

That narrowness is what makes it portable and testable, and it is also where the ceiling sits. As soon as a request needs the previous turn, needs to decide when to search, or needs to hold a role across calls, it is no longer a task prompt. It is an agent prompt, and the rules on this page stop applying.

Everything written inside also competes for the same attention. A three-paragraph role does not improve a classifier's output; it delays it. "Summarise the report in three sentences for someone with two minutes" does more work than "you are a world-class summariser with twenty years of experience", in one line instead of four.

What is left is a contract with four parts: what goes in, what comes out, what comes back when the input cannot produce a valid answer, and how you know the answer is any good.

## The input is described, not assumed

A task prompt does not have the context of the conversation that produced it. Write "summarise the document above" or "classify the data I sent you" and the model has neither the document nor the data: it has whatever arrived inside the call. If the material is missing, it fills the gap with something plausible.

Describing the input does three things: it names the material, says what shape it arrives in, and decides what happens when a piece is missing. Optional fields are the ones that do the most damage, because they are the ones the model invents when nobody has told it they can arrive empty.

```text
Classify each ticket by product area.

Allowed areas: billing, access, integrations, data, cannot determine.

<tickets>
[
  {"id": "A-1", "subject": "Cannot sign in with Google", "description": "The Google button has returned error 400 since yesterday.", "customer": "Acme"},
  {"id": "A-2", "subject": "March invoice is duplicated", "description": "You have charged me twice for the same month.", "customer": null}
]
</tickets>

Decide from `subject` and `description`. `customer` is optional: it does not
change the area and does not appear in the answer. Do not use list order as a
signal.

Return a JSON array with one object per ticket:
{"id": "the id you received", "area": "one of the allowed areas", "reason": "at most 15 words, quoting the words in the ticket that decide the area"}

Nothing before or after the array.
```

The two records are not decoration: one carries `customer` and the other carries `null`, and the prompt says what to do with that difference. Had the list arrived as loose paragraphs, that missing field would have gone unnoticed until the first strange answer.

## The output is described field by field as well

A field called `priority` accepts anything until the prompt says it holds `high`, `medium` or `low`. Same with a date: unformatted, three different ones turn up in the same batch. The field's name is not the specification. The specification is what you write next to it.

Describing each field does two jobs. For whoever consumes the answer, a `json.loads` needs a clean object, without a "Here is the JSON:" in front of it. For the model, it forces the count, the length and the order to be decided before the first answer arrives, which is the only moment that decision is still yours.

```text
Summarise the report below for someone with two minutes to spare.

<report>
[paste the report text here]
</report>

Return a JSON object with three keys and nothing else:
- "headline": one sentence of at most 12 words, with no evaluative adjectives.
- "summary": three consecutive sentences in a single field, at most 60 words,
  carrying the figures exactly as they appear in the report.
- "key_figures": a list of up to three strings, each holding a figure and its
  unit.

Write in British English. Do not use markdown or bullet points. If the report
contains no figures, "key_figures" is [].
```

None of those three keys needs a paragraph of explanation: each fits on a line, and all three can be checked against the answer without asking the author what was meant. That is the bar.

## When the input cannot deliver, the output says so

Forcing the shape onto data that cannot support it produces a false value in the right format. That is worse than a visible gap: the gap shows up in review, the false value shows up in production three weeks later.

The rule is that the gap is a value in the contract, not a polite sentence inside the prose. `null`, "cannot determine", or a list of the fields that are missing. Then whoever consumes the answer detects it with a comparison instead of reading the whole thing to find out.

```text
Extract the renewal terms from each contract.

<contracts>
[{"id": "C-1", "text": "..."}]
</contracts>

Return a JSON array, one object per contract, with these keys:
- "id": the id you received, copied unchanged.
- "renewal_date": a date as YYYY-MM-DD, or null if the contract does not fix one.
- "notice_days": an integer number of days, or null if it is absent.
- "missing_fields": the list of keys above that came back null, plus "annex"
  when the contract refers to one that is not in the text; empty list if
  nothing is missing.

Use only the contract text. Do not infer the date from the term or the billing
period. If the contract refers to an annex that is not in the text,
"renewal_date" is null.
```

There is a second gap that is easier to miss: the whole task. A contract written in another language, a three-line text, or an invoice scanned as an image are not rare cases; they are the normal input of a system that has been in production for a month. If you have not decided what comes back there, the model decides for you.

## A batch, or one call per item

Putting twenty items in one call is cheaper and produces answers that are more consistent with each other, because the model sees the same criterion applied twenty times in a row. It also concentrates the risk: one badly resolved item drags the criterion of the ones after it, and if the answer carries no identifiers, there is no way to tell which one failed.

One call per item costs more and isolates the failure. The prompt stays short, a retry touches only what failed, and one item's answer cannot contaminate another's.

The decision, in three lines:

- **Batch** when the transformation is the same for all of them, the output carries an id you supplied, each item is short, and you can tolerate one dragging another.
- **One at a time** when the material is long (a contract, a report), when the criterion depends on the item as a whole, or when you need to retry separately.
- **Never** by asking the model to "remember the previous ones" or to "carry on with the next ones". There is no memory between calls, so there is nothing to remember: whatever item is not in the batch is gone.

```text
Translate the interface strings in the batch into British English.

<strings>
[
  {"key": "save_changes", "text": "Save changes"},
  {"key": "connect_sso", "text": "Connect SSO"},
  {"key": "delete_workspace", "text": "Delete {workspaceName} workspace?"}
]
</strings>

Return a JSON object with one key per `key` received and the translation as the
value. Do not add keys, do not omit any, do not change the order.

Do not translate product names, acronyms or the content inside braces.
Sentence case for buttons, no trailing full stop.
```

With one object per key, the count is a one-line check: if the number of keys in the answer does not match the input, an item was dropped and the retry can be aimed. Without identifiers, the only option is to run the batch again and hope for something different.

## One example, and only where the description runs short

Most task prompts need no examples: the objective and the output format already carry the contract. They are needed where the shape is easy to misread. A classification scheme with two categories that touch, a field whose name does not say what belongs in it, a tone easier to show than to describe.

Two rules keep an example adding rather than subtracting. Each one goes in its own container, with the input and output halves labelled the same way in all of them: a stray example in the middle of the text reads as material to process. And the example's format has to match the format you ask for, because an example teaches the wrong shape as reliably as the right one.

In the classifier from the first section, the fine edge sits between "access" and "integrations", and a sentence of prose does not settle it. Two examples do:

```text
<examples>
input: {"subject": "The password reset email never arrives", "description": "I have requested it three times this morning and nothing comes through."}
output: {"area": "access", "reason": "the user cannot complete the reset"}

input: {"subject": "Shopify webhook arrives empty", "description": "The endpoint receives the event with no body."}
output: {"area": "integrations", "reason": "the failure is in the delivery of an external event"}
</examples>
```

The block is pasted into the prompt, just before `<tickets>`. The first example sits far from the edge and fixes the format; the second sits on the edge and settles the case the prose did not.

## You test it against a list, not against a feeling

The only test of a task prompt is the output, and comparing an output needs another one. Before you ship the prompt, write the cases: ten real inputs from the system that will call it, three awkward ones (an empty field, text in another language, material three times longer than usual) and the expected output for each. Anything you cannot fill in on the expected-output side is a gap in the contract, not in the test.

With that list, every change to the prompt becomes a comparison. Change one clause at a time and keep the version that passes, not the version that reads best. Four checks can be automated without writing a real test: the answer parses, it carries no extra keys, the item count matches the input, and the gap value appears when the field is missing.

You can also ask the model to review the contract, with the prompt and the inputs in front of it:

```text
Here is a task prompt and three test inputs. Do not run the task.

<task_prompt>
[paste the prompt]
</task_prompt>

<inputs>
[paste the three inputs]
</inputs>

Return a JSON array of gaps in the contract. Each gap carries:
- "gap": the part of the prompt that is missing or contradicts itself.
- "input": which of the three triggers it.
- "fix": the exact sentence to add, in one line.

Look for four things only: undescribed input fields, output fields that cannot
be checked, no value for incomplete input, and two rules that contradict each
other. If you find none, return [].
```

## When it misbehaves

| Symptom | Cause | Fix |
| --- | --- | --- |
| Returns the JSON wrapped in prose ("Here is…") | the output was named in prose, with no skeleton | paste the skeleton and add "nothing before or after" |
| Invents a date or an amount that is not in the material | an undescribed field with no gap value | declare `null` and the missing-fields list |
| Items go missing from a batch of twelve | the output carries no identifiers from the input | require the id copied unchanged and the same count |
| The format changes between two identical runs | two sources of shape, prose and example, and they disagree | leave one source and align the example with it |
| A rule is ignored once the input gets long | the rule and the material compete, undelimited | wrap the input in its own container |
| It asks clarifying questions nobody will answer | agent rules slipped in ("ask if anything is unclear") | remove them: the gap is declared in the output |
| It opens with "as we discussed earlier" | a multi-turn assumption inherited from another prompt | delete every reference to earlier turns |

## What changed, and when

- **1 November 2026.** This guide replaces the task-prompt guide that came before it: its old URL redirects here. The coverage section is derived from the `task` skill rather than typed by hand: when the skill changes, the page follows without anyone editing the Markdown.
