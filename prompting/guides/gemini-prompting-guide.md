---
disabled: true
---

# Prompting for Gemini: Gemini 4 Argon and the 3.x family

**Source:** [https://systempromptmaster.com/learning/gemini-prompting-guide](https://systempromptmaster.com/learning/gemini-prompting-guide)
**Downloaded:** 2026-11-10

**Description:** How to write prompts for Gemini 4 Argon and the 3.x family: the four input shapes, `thinking_level`, the parameters the API ignores, and context-first ordering.

> **Quick answer:** Name the shape of the input, set `thinking_level` instead of asking for steps, drop `temperature` and `top_p` because they are ignored, stop prefilling model turns, put context before instructions on long inputs, and turn on Google Search or code execution when the answer depends on recent facts or arithmetic.

Gemini takes an instruction in four different shapes, and how long it thinks before answering is decided by a request parameter, not by a sentence in the prompt. Meanwhile three of the dials you used to turn are ignored, and prefilling the model turn returns an error.

## Name the shape of the input: question, task, entity or continuation

Google's documentation starts prompt design with four input shapes —question, task, entity and continuation— and naming yours is the first lever: the input already states the question and the shape of what you want back.

```text
What would you call a flower shop that specialises in dried-flower bouquets?
Give me a list of 5 options, just the names, no explanation.
```

The taxonomy dates from the 2.5 generation and its examples are still labelled `(gemini-2.5-flash)`; nothing says how the four shapes behave on `gemini-4-argon`.

What did change is length, and here Google contradicts itself: the page still carries a 2.5-labelled example asking for comprehensive answers by default, while its Gemini 3 principles say the model answers directly and efficiently unless you ask for detail. Both sentences are live and unreconciled; length is something you request.

## The thinking level decides how much it thinks, not a sentence in the prompt

Reasoning happens before the visible answer and `thinking_level` governs it: `low`, `medium` and `high` across most of the line, `minimal` where it is supported, and a default that varies by model. `gemini-4-argon`, `gemini-3.8-flash` and `gemini-3.6-flash` start at `medium`, `gemini-3.5-flash-lite` at `minimal`, and `gemini-3.1-pro-preview` and `gemini-3-flash-preview` at `high`. The control used to be called `thinking_budget`.

The second contradiction is in the reasoning advice: the best-practice template ends with `<final_instruction>Remember to think step-by-step before answering.</final_instruction>`, and the reasoning section of the same page says it is generally not necessary for the model to detail its steps. Google publishes both without reconciling them. What is settled is the split: depth lives in the parameter.

The short nudge is documented in both directions:

```text
Think the problem through before answering. Do not write the reasoning out:
return the conclusion and the two sentences that support it.
```

## Sampling parameters are accepted and ignored

`temperature`, `top_p` and `top_k` are deprecated: the API accepts them and ignores them, and will return an error in future model generations. `candidate_count` is unsupported from Gemini 3 onwards.

A grid search over those values does not measure what you think it does: the run-to-run difference comes from somewhere else, and the page's remedy for a safety-filtered response —raise the temperature— now does nothing. For determinism, define a system instruction with explicit rules:

```text
system_instruction:
  Always answer in three bullets, in this order: what happened, what it means,
  what to do next. Twenty words per bullet at most. If a fact is missing, write
  "no data" in that bullet instead of filling it in.
```

## A prefilled model turn returns 400

If the last non-empty turn in the request is a `model` turn, the API returns a `400`. The usual case was opening the assistant's reply with the first characters, to suppress a preamble or force JSON.

There are two replacements: `system_instruction` for a formatting rule and structured outputs for a schema. A prefix as text still works inside the user turn, which is what the page calls the completion strategy:

```text
Write the report in this structure and start at the first section, without
any introductory sentence:

1. Summary
```

## Context first, instructions last

With a large input you supply all the context first and the instruction or question at the end. It is one of the three principles the documentation labels Gemini 3, and it is written as a requirement.

On the unified 1,048,576-token window of `gemini-4-argon`, interleaving instructions and evidence across that distance works against the rule. A transition phrase —"Based on the information above…"— goes between the material and the question: it marks where the evidence ends and the request starts.

```text
<context>
[paste the contract, the report or the files here]
</context>

Based on the information above, give me five bullets on which obligations the
supplier accepts and which do not appear in the document.
```

## When a fact or a sum is missing, the tool is part of the prompt

Grounding with Google Search connects the model to real-time web content and belongs on whenever it may need an obscure or recent fact. Code execution lets it generate and run Python and belongs on whenever the task involves arithmetic, counting or calculation. Both are request switches, not behaviours you talk the model into: a prompt that asks it to look something up or add numbers without the tool is asking for the failure the tool exists to prevent.

For the knowledge cutoff the page publishes a literal clause, `Your knowledge cutoff date is January 2025.`, in the page's last update of 2026-10-13, for models released in 2026. It is reproduced as published; check it against the model card for the endpoint you use.

```text
system_instruction:
  For time-sensitive user queries that require up-to-date information, you
  MUST follow the provided current time (date and year) when formulating
  search queries in tool calls. Remember it is 2026 this year.
```

## When it misbehaves

**The answer is terse when you wanted detail.** That is the line's default, and the instruction asking for comprehensiveness comes from the 2.5 era. Ask for the length.

**The answer is cut off or comes back empty.** `max_output_tokens` also counts thought tokens, and the model stops mid-reasoning with status `incomplete`. Raise the ceiling or lower `thinking_level`.

**Changing `temperature` changes nothing.** It is ignored. Put the rule in the system instruction.

**Every call returns `400`.** The last non-empty turn is `model`. Move the prefix into the user turn, or use `system_instruction` and structured outputs.

**It invents a fact from this year or gets the arithmetic wrong.** No tool is on. Enable Google Search grounding or code execution.

## What changed, and when

- **21 July 2026.** The deprecation of `temperature` , `top_p` and `top_k` is announced: they are accepted and ignored.
- **8 October 2026.** `gemini-3.7-flash` is routed to `gemini-3.8-flash` and `gemini-3.5-flash` to `gemini-3.6-flash` : the old endpoint is answered by its successor.
- **13 October 2026.** Gemini 4 Argon becomes generally available. It is the only Gemini 4 model: there is no Gemini 4 Pro and no Gemini 4 Flash.

Coming from the 2.5 generation: remove the three sampling parameters, replace the prefilled model turn with `system_instruction` or structured outputs, move the context ahead of the instructions, and turn on the tool you were missing.

## Sources

- [https://ai.google.dev/gemini-api/docs/prompting-strategies](https://ai.google.dev/gemini-api/docs/prompting-strategies)
- [https://ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models)
- [https://ai.google.dev/gemini-api/docs/changelog](https://ai.google.dev/gemini-api/docs/changelog)
- [https://ai.google.dev/gemini-api/docs/deprecations](https://ai.google.dev/gemini-api/docs/deprecations)
- [https://ai.google.dev/gemini-api/docs/models/gemini-4-argon](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon)
- [https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)
- [https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview)
- [https://ai.google.dev/gemini-api/docs/thinking](https://ai.google.dev/gemini-api/docs/thinking)
- [https://ai.google.dev/gemini-api/docs/latest-model](https://ai.google.dev/gemini-api/docs/latest-model)
- [https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.8](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.8)
- [https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.6](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.6)
- [https://ai.google.dev/gemini-api/docs/text-generation](https://ai.google.dev/gemini-api/docs/text-generation)
- [https://ai.google.dev/gemini-api/docs/interactions-overview](https://ai.google.dev/gemini-api/docs/interactions-overview)
- [https://blog.google/innovation-and-ai/technology/developers-tools/build-with-gemini-4-argon/](https://blog.google/innovation-and-ai/technology/developers-tools/build-with-gemini-4-argon/)
