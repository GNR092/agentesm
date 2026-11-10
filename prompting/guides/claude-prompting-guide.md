---
disabled: true
---

# Prompting for Claude: Opus 5.5, Sonnet 5.5 and Haiku 5.5

**Source:** [https://systempromptmaster.com/learning/claude-prompting-guide](https://systempromptmaster.com/learning/claude-prompting-guide)
**Downloaded:** 2026-11-10

**Description:** How to write prompts for Opus 5.5, Sonnet 5.5 and Haiku 5.5: `effort` as the primary control, an append-only history, and verification per model.

> **Quick answer:** Set effort as a parameter instead of asking for it in the prompt, append every assistant turn byte for byte with its thinking blocks, inject reminders as mid-conversation system messages, and add or remove verification per model: out on Opus 5.5, in on Sonnet 5.5 and Haiku 5.5.

Two things left the prompt in this generation. How hard the model thinks is now a parameter, and the shape of the conversation is now your harness's job. The prompt still decides what you get. It no longer decides what it costs to think about it.

## Effort is the setting, and the number does not travel

`effort` is the main lever on thinking depth, quality, latency and cost. There are five levels —`low`, `medium`, `high`, `xhigh`, `max`— with a per-model default: `medium` on Opus 5.5, `high` on Sonnet 5.5 and `medium` on Haiku 5.5.

The names do not mean the same amount of thinking everywhere: Opus 5.5 at `medium` matches or beats Opus 5 at `high`. A prompt tuned at `high` on the previous generation is not tuned at `high` on this one, so the sweep gets run again on the new model.

Two plumbing traps. Changing top-level `effort` between requests invalidates the prompt cache; the per-message change in the `mid-conversation-output-config-2026-07-01` beta keeps it. And `budget_tokens` is dead: it returns 400 from Claude 4.7 onward.

Reasoning is not something you ask for in writing either. A prompt telling the model to write its steps in `<thinking>` tags may be declined, and asking it to restate that reasoning trips the `reasoning_extraction` category. Lean on thinking, and lower `effort` when cost is the problem.

```text
Request parameters. None of this belongs inside the prompt:
effort = medium    # Opus 5.5 medium · Sonnet 5.5 high · Haiku 5.5 medium
# Changing it between requests invalidates the prompt cache.
```

## History is append-only

The largest correctness constraint in this generation: every assistant turn goes back into the history byte for byte as the API returned it, thinking blocks included. Earlier turns are not edited, `system` and `tools` are not rebuilt between requests, and nothing is summarised in place.

On Claude 5.1 and later any of those edits invalidates every later thinking block in the conversation, and a prefix that does not line up can raise `bound to a different conversation`. `thinking.block_binding.prefix_mismatch_behavior`, with `"error"` and `"drop_block"` in the `thinking-binding-controls-2026-08-01` beta, decides which failure you get.

What you do instead is put the reminder in a mid-conversation or turn-scoped system message, in the `mid-conversation-system-clear-at-2026-08-21` beta. Rewriting the top-level `system` prompt to bolt a reminder onto it is the failure this replaces.

```text
System message inserted mid-conversation:

Reminder from here to the end of the conversation: [the new rule].
```

## There is no temperature left, so say what you want

`temperature`, `top_p` and `top_k` were removed in API version `2026-10-21`, and setting any of them returns 400. The vendor's advice is to omit them and steer the behaviour from the prompt.

If you leaned on `temperature: 0` for steady output, you now say what steady means: same format, same sections, same order. If you raised `top_p` for variety, ask for the variety you wanted.

What is left is effort plus explicit format and length instructions. On Sonnet 5.5 and Haiku 5.5 thinking and replies get much longer at `xhigh` and `max`, which are for work where a gain has been measured.

```text
Return the brief in four sections, in this order: Summary, Evidence,
Risks, Next step. If a fact is not in the context, write "no data" on
that line rather than filling it with an estimate.
```

## Verification goes in or comes out, per model

Remove it on Opus 5 and Opus 5.5. Both verify their own work without being told, and carried-over instructions —"include a final verification step", "use a subagent to verify"— cause over-verification: extra tokens and latency for no gain in quality. Those lines get deleted, not reworded.

```text
Lines to delete when moving to Opus 5.5:
"Include a final verification step for any non-trivial task."
"Use a subagent to verify your work."
```

Add it on Sonnet 5.5 and Haiku 5.5: both report a change as done without having run the check that exercises it, at `low` and at `medium` effort.

```text
Before you call a change done, run the check that exercises it: the test
or the command that touches the code you just wrote. If a dependency is
missing, install it with the project's own package manager, never with
sudo. If it fails, say so with the output.
```

## When it misbehaves

**A rule stops applying three turns in and the thinking arrives empty.** The harness rewrote `system` to bolt the reminder on, or rebuilt `tools` between requests, and on Claude 5.1 and later that invalidates every later thinking block. Move the reminder into a mid-conversation system message and stop touching the prefix.

**The request returns 400 with nothing else to go on.** It is almost always `temperature`, `top_p` or `top_k`, removed in `2026-10-21`; `budget_tokens`, from Claude 4.7; `thinking: {"type": "disabled"}` on Opus 5.5, where thinking cannot be switched off; or `tool_choice` of type `any` or `tool` on Opus 5.5 and Sonnet 5.5. It is a request problem, not a wording problem.

**It ends the turn describing what it is about to do next.** A text-only `end_turn` is a report, not evidence that the work is finished. Without guidance the model closes the turn on the next step, or asks permission for something the request already authorised. Tell it nobody is watching and to carry on with what is reversible.

## What changed, and when

- **21 October 2026.** API version `2026-10-21` : `temperature` , `top_p` and `top_k` are gone, and setting them returns 400.
- **7 October 2026.** Claude Haiku 5.5, the first Haiku with effort levels. `medium` by default, and `disabled` accepted only up to `high` .
- **28 September 2026.** Claude Sonnet 5.5: `between_tools` replaces `disabled` as the thinking floor.
- **30 November 2026.** Sonnet 4.5 retires; Haiku 4.5 and Opus 4.5 are close behind.

Coming up from the previous generation: run the effort sweep again, drop `budget_tokens`, stop rebuilding `system` and `tools`, move reminders into mid-conversation messages, fix verification per model, and drop sampling.

## Sources

- [https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1)
- [https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5)
- [https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5)
- [https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-haiku-5-5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-haiku-5-5)
- [https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)
- [https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview)
- [https://platform.claude.com/docs/en/models/overview](https://platform.claude.com/docs/en/models/overview)
- [https://platform.claude.com/docs/en/about-claude/model-deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations)
- [https://platform.claude.com/docs/en/release-notes/overview](https://platform.claude.com/docs/en/release-notes/overview)
