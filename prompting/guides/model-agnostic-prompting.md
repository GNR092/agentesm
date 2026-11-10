---
disabled: true
---

# Prompting that works on any model

**Source:** [https://systempromptmaster.com/learning/model-agnostic-prompting](https://systempromptmaster.com/learning/model-agnostic-prompting)
**Downloaded:** 2026-11-10

**Description:** How to write a prompt that does not depend on the vendor: role and task, checkable constraints, the exact shape of input and output, and delimiters.

> **Quick answer:** Write the prompt with an explicit role and task, constraints a reviewer can check, the exact shape of input and output, stable delimiters, marked examples and only the reasoning somebody will read; effort and sampling are set on the request, not in the text.

A prompt that survives a change of model is not the one that dodges the differences between GPT-6, Claude Opus 5.5 and Gemini 4 Argon: it is the one that does not depend on them. All three accept the same architecture — role, task, constraints, input, output, examples — and on all three the levers that used to be argued about inside the prompt — reasoning depth, sampling, prefilling the reply — are now arguments of the call.

What follows is the part of the craft that survives a change of vendor. Every rule carries a prompt you can paste; the gaps in square brackets and the names in angle brackets, such as `<text>` or `<sources>`, are yours to fill. Where a lever is no longer written in the prompt, the section says so and sends you to the guide for that vendor.

## A two-sentence role and a task with a verb

The role sets the judgement; the task says what gets delivered. They stay separate because they do different jobs: "you are a copy editor for a Spanish-language newspaper" steers the judgement on every later sentence, and "split every sentence over 30 words into two" says what the product is.

Without a role, every rule has to justify itself. Without an explicit task, the model decides what it is doing, and you do not see that decision until the answer arrives.

```text
You are [role: a copy editor for a Spanish-language newspaper, with newsroom
standards].
Your task is [verb + object: split every sentence over 30 words in the three
paragraphs inside <text> into two, without reordering the ideas].
```

Two sentences is enough. A role that grows into a biography spends attention before the instructions start, and a task split across three sentences that each suggest a different deliverable leaves the choice to the model. If there really are two deliverables, that is two prompts or two delimited phases.

## Constraints a reviewer can check

A constraint earns its place when someone can look at the answer and say whether it held. "Be careful" cannot be checked; "use only the material inside `<sources>`" can.

Describe what you want to see first, and name the failure only afterwards, and only if it is likely. "Write in flowing prose, without bullet points" is easier to follow and easier to check than a list of three banned formats, and it leaves no doubt about what to do with the information that fell outside the list.

```text
Constraints:
- Use only the material inside <sources>.
- Write in flowing prose, without bullet points or bold text.
- Three sentences at most.
If the input makes a constraint impossible to meet, say so on the first line
instead of working around it.
```

Do not stack prohibitions. Ten prohibitions about things the model was never going to do dilute the two that matter, and two constraints that contradict each other — concise but complete, creative but literal — cancel out without any error being raised. Where a rule has a reason, one clause of rationale replaces three clauses of enforcement: a model that understands why the constraint exists generalises it to the cases you did not enumerate.

## Input, output and a success criterion

Say what goes in, in what shape, what comes out, and how it is checked. The input half is a list of field, format, and what to do with what is missing. The output half is the shape, the fields, the length, the tone and the language.

The success criterion turns "a good answer" into something the model can aim at and you can review: cite the source for every fact, return at most five items ranked by impact, name the file the change belongs in. If a reviewer cannot apply the criterion without asking what you meant, it is not a criterion.

```text
Input: one email inside <email>. If the order number is missing, do not infer it.

Output: a JSON object with these keys.
- "order": the number as it appears in the email, or null.
- "reason": one of these three strings: "refund", "exchange", "other".
- "reply": two sentences in British English, second person singular.

Success criterion: if the email does not determine the reason, "reason" is
"other" and "reply" asks for the missing fact. Return nothing outside the JSON.
```

A field name does not say what goes in it. A field called "reason" holds anything until the prompt lists the three valid values. And when a machine consumes the answer, one worked example of valid output reads better than a paragraph describing it.

When the input cannot support a valid answer, define the emergency exit before you need it: ask for the missing fact, state the assumption you are making, or return an explicit "cannot determine". Forcing the shape the data does not support produces a valid JSON object with an invented claim inside it.

## The same delimiters for the same material

Each kind of content gets its own container, and the container does not change halfway through the prompt or between revisions. Instructions, context, examples and input are four different things; put them in one block and the model infers the boundaries from position alone, which is the first thing an edit disturbs.

```text
<instructions>
[what does not change between requests]
</instructions>

<context>
[what changes on every call]
</context>

<input>
[material the user submitted]
</input>
```

XML-style tags, Markdown headings or a fence of dashes all work. What matters is never using two markers for the same content or one marker for two kinds. With the sections labelled, a reviewer can see where each rule lands and spot the one that drifted into the example block.

The same discipline pays off when code assembles the prompt: the fixed shell stays identical between calls and only the content slot changes. Caching then behaves as you expect, and a per-request value is not mistaken for a standing rule.

## Two to five examples, marked as examples

An example fixes a shape better than any description. Two or three show that the pattern generalises and where its edge sits; past five you spend attention and gain no information.

Choose examples by moving the surface and holding the pattern still, and include at least one odd case that the instructions only describe in the abstract. That is the case a model gets wrong when it has only the description.

```text
<examples>
<example>
<input>I want to return the headphones, order 4471.</input>
<output>{"order": "4471", "reason": "refund", "reply": "[two sentences]"}</output>
</example>
<example>
<input>I got the wrong size and I cannot find the order number.</input>
<output>{"order": null, "reason": "exchange", "reply": "[two sentences asking for the number]"}</output>
</example>
</examples>

Now process the input inside <input>.
```

Examples are marked so they cannot be read as instructions, and so the live request is not mistaken for one of them. Label both halves with the same prefixes, wrap each demonstration in its own container, group the set in an outer one. And do not vary the formatting inside the set: one example with headings and another with tags teaches the inconsistency as reliably as it teaches the pattern.

## Format is written once

Format is specified, not remembered. Once, where the output goes: a JSON object with these keys, a Markdown table with these columns, three short paragraphs, one sentence per item. Repeating "format the answer correctly" three times adds no information and takes up room.

```text
Return the analysis in three parts, in this order:
1. "Summary": one paragraph of three sentences, in prose.
2. "Findings": a Markdown table with the columns Finding, Evidence, Impact.
   Five rows at most, ordered by Impact, highest first.
3. "Next step": one sentence in the imperative.
Do not add sections or commentary outside these three.
```

Order and length are format too: which section comes first, how long each part runs, what the model may leave out. If the answer follows a template, show the skeleton with the variable parts marked and state how many entries you expect when the count is bounded.

Format that contradicts another rule — 100 words for a section that also has to be exhaustive — is the most common cause of an answer that follows the format and misses the job. Resolve the conflict in the prompt, not in review.

## Ask for the reasoning you need, not the ritual

Ask for the reasoning the task needs and nothing more. If the answer rests on a calculation or a comparison somebody will audit, ask for the work shown, labelled and separated from the conclusion. If it is a decision the model can reach internally, ask for the decision and its justification in a sentence.

"Think step by step" helps when the steps are the deliverable and gets in the way when they are not: it pads every answer with process and pulls attention away from the result.

```text
Before the answer, write a section "Checks" listing the data you compared to
choose the reason, one per line. Then the JSON.
Do not explain how you reached each check.
```

Prefer a general instruction about the reasoning over a hand-written sequence of steps. A sequence pins the model to your picture of the problem; a goal with its criteria lets it bring its own reasoning, including the moves you did not anticipate. Where the process itself is the requirement — a compliance checklist, a fixed order of calculation — write the sequence out and say the order is mandatory, so it is neither compressed nor reordered.

## The lever moved into the request

The three levers that used to be settled inside the prompt are now arguments of the call, and each vendor names them differently.

| What you control | OpenAI | Anthropic | Google |
| --- | --- | --- | --- |
| Reasoning depth | `reasoning.effort`, from `none` to `max` | `effort`, from `low` to `max` | `thinking_level`, from `low` to `high`, and `minimal` on some models |
| Sampling: `temperature`, `top_p`, `top_k` | removed from the request when effort is not `none` | removed; sending them returns 400 | ignored |
| Prefilling the model turn | no documented 400 | 400 | 400 |

The names do not transfer. An Anthropic `high` and a Google `high` are not the same amount of thinking, the available rungs differ by model, and so does the default: changing model means re-sweeping effort, not copying a number.

No lever fixes what is badly written. A badly specified task, reasoned over for longer, reaches the wrong target more slowly and more expensively. What recovers quality is the prompt.

And sampling is no longer a formatting lever. If you lowered `temperature` to make output consistent, the replacement is a system instruction with explicit rules, structured output and a test suite that compares answers. Prefill works the same way: what you did by starting the model's reply yourself is now done with the system instruction or with structured output.

The available values, the ones that return 400 and the per-model defaults live in the [OpenAI guide](https://systempromptmaster.com/learning/openai-prompting-guide), the [Claude guide](https://systempromptmaster.com/learning/claude-prompting-guide) and the [Gemini guide](https://systempromptmaster.com/learning/gemini-prompting-guide). They are not repeated here because they change with every generation.

## When it misbehaves

**A rule that held at the start stops applying.** It is not the model: the rule lived in a block that is no longer resent, or it ended up buried under the context of the first calls. Whatever has to survive the whole conversation goes in the fixed part of the prompt and is sent with every request; whatever changes goes in the content slot.

**The answer follows the format and is useless.** Almost always two rules contradict each other — 100 words and exhaustive, five findings and be brief — or a field was never defined. Fix it in the prompt, not in review: decide which rule wins and write the tie-break in one line.

```text
When the length limit and the checklist conflict, the limit wins: cut the
explanation, never the items in the list.
```

**The model answers an example as if it were the request.** The examples are neither grouped nor labelled, so the last one reads as the live input. Put the set in a container and close with "now process the input inside `<input>`".

**The answer fills with process nobody reads.** "Think step by step" was asked for on a decision that needs no audit. Ask for the decision and its justification in a sentence, and save the visible work for the tasks somebody will review.

## Before you ship it

Read the prompt top to bottom the way the model will: with no memory of the conversation that produced it. Three questions, in this order. Is the task clear to someone without your context? Can every constraint be checked by looking at the output? Are any two rules contradicting each other, including an exception that contradicts the general rule?

Then the scope. A task so broad that any answer qualifies is not specified; one so narrow that no judgement is left cannot handle the inputs you have not seen.

And four quick checks: the success criterion matches the format you asked for, the examples use the same structure as the live request, the emergency exit is defined for the cases you can anticipate, and the prompt does not ask for reasoning, detail or length that no reader will use.

```text
Review the prompt inside <prompt>. Return a list with:
1. The task in one sentence, as someone without context would read it.
2. Each constraint, and whether looking at the output can check it.
3. The pairs of rules that contradict each other, quoting both.
4. What the prompt asks for that no reader will use.
Do not rewrite the prompt yet.
```

Changing one thing at a time and comparing the outputs is part of the work, not a sign that the prompt was wrong. You keep the version that works, not the one that sounds best.

## What changed, and when

- **21 October 2026.** Anthropic's API version `2026-10-21` removes `temperature` , `top_p` and `top_k` : sending them returns 400. ( [model deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) )
- **20 October 2026.** OpenAI's prompt cache goes to 12 hours, with cache writes at 2.5× the input price. The fixed part of the prompt stops being a matter of style. ( [changelog](https://developers.openai.com/api/docs/changelog) )
- **3 September 2026.** GPT-6 Astra accepts no custom `temperature` or `top_p` . ( [latest model guide](https://developers.openai.com/api/docs/guides/latest-model) )
- **21 July 2026.** Google deprecates the three sampling parameters and ignores them; prefilled model turns return 400. `thinking_budget` is renamed `thinking_level` . ( [what's new in Gemini 3.6](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.6) )
- **28 May 2026.** Anthropic returns 400 if you send `temperature` , `top_p` or `top_k` with any value other than the default. ( [release notes](https://platform.claude.com/docs/en/release-notes/overview) )

With that in hand, the order of work when you change model is: take effort, sampling and prefill out of the text; check that the fixed part is resent with every request; and go back to the vendor guide for the names and values.

## Sources

- [https://developers.openai.com/api/docs/guides/prompt-engineering](https://developers.openai.com/api/docs/guides/prompt-engineering)
- [https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [https://ai.google.dev/gemini-api/docs/prompting-strategies](https://ai.google.dev/gemini-api/docs/prompting-strategies)
