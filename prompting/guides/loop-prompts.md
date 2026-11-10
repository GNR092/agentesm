---
disabled: true
---

# Loop prompts: agents that repeat until a condition holds

**Source:** [https://systempromptmaster.com/learning/loop-prompts](https://systempromptmaster.com/learning/loop-prompts)
**Downloaded:** 2026-11-10

**Description:** How to write a prompt that repeats: the boundary between runs, the exit condition as a check against stored state, and the report after repeated failures.

> **Quick answer:** State what counts as a new run, write the exit condition as a check against stored state, decide where anything that survives a run lives, and say what the loop does after repeated failures; without those four parts it repeats work or fails in silence.

A task prompt finishes and forgets. A loop prompt does not: the next run inherits what the last one left behind, and that is where nearly all of its failures come from. The model does not remember the previous run; it sees only what the prompt puts in front of it. If the prompt does not say where state is read from and where it is written, run twelve either repeats work or loses what it did.

There are two shapes. Recurring: the same action at a fixed cadence — every morning, every five minutes, on each webhook — and each run stands alone. Iterative: the action stays the same but the result evolves — poll until ready, retry until accepted — and each run depends on the one before it.

A loop needs four things a single call does not: a boundary between runs, a condition that can be checked, somewhere for state to live, and a plan for when the condition never arrives.

## A new run is not a continuation

The model cannot tell whether the message it just received is the second turn of a conversation or the twentieth run of a loop: it knows what is in the request. If nobody tells it that it starts from zero, it carries the opposite assumption, continues work already done, or asks about state that does not exist.

So the boundary gets written: run identifier, start time, run number, and which unit this run claims. One explicit sentence: no memory of the previous run. One run, one unit; if it processes "some" items, it chooses, and it will choose what suits it.

```text
Run [run_id], start [ISO timestamp], run [n] of [N].

You start from zero: you have no memory of the previous run. Everything you
know about it comes from the `loop_state` table, row `[name]`, which you read
on the way in and update on the way out.

One run is one unit: the oldest row in `[table]` with `status = 'pending'`, by
`created_at`. If there is none, stop and say so.

Order: check the exit condition, do the work, record the outcome, prepare the
next run. Do not process a second unit.
```

## The exit condition is written as a check

A condition that cannot be checked from outside is not a condition; it is an intention. "When the report looks right" leaves the agent deciding when to stop, and that agent has two endings: it stops early, or it does not stop.

Write it as an observable fact: the queue is empty, `done` on the batch rows, the service answering cleanly for ten minutes straight, the retry maximum reached. Read it from a table or a tool output, never from its own summary. And decide whether it is evaluated before or after the work, what the loop returns when it exits, and what the budget is.

```text
Exit condition, checked at the start of every run:

- Success: `[table].status = 'done'` on the [N] rows with `batch_id = "[id]"`.
- Abandonment: `attempts >= 5`, or `deadline` has passed.
- Wait: if attempts remain, stop and leave `next_check_at`.

Evaluate against the state you read from the database or from the tool output.
"It should be ready by now" is not a check.

Return only: {"exit": "success" | "budget" | "blocked", "pending": 0,
"last_error": null}
```

## State lives outside the conversation

What survives cannot live in the conversation: restart the process and it is gone. The attempt counter, the identifiers already processed and the accumulated result go to something durable, with a name and fields, and the next run reads them before doing anything.

Write the update rule — what gets written at the end, and with what value — and what gets thrown away: reasoning notes, transient errors, summaries. And write the state before replying: if the run dies halfway, the next one needs to know where it stopped.

```text
State: table `loop_state`, one row per loop. Read it on the way in, write it
before replying.

- last_run_at: when this run started.
- cursor: `id` of the last completed unit.
- attempts: +1 on start; 0 when a unit succeeds.
- last_error: literal message from the last failed run, or null.
- paused: true on escalation; do not set it back to false yourself.

Your reasoning notes and transient network errors do not persist.
```

## What already happened does not happen twice

A run can execute twice: the process restarts, the schedule fires late, two workers overlap, or a retry follows a timeout whose first request actually succeeded. In all four cases the effect already happened and the prompt believes it did not.

The guard follows the effect. For work that can repeat harmlessly, a processed marker is enough. For anything visible outside — email, charge, post, closed ticket — the check comes before the action. And a timeout does not say whether the call arrived: there you read the real state of the resource instead of retrying blind.

```text
Before any effect visible outside the system — email, charge, post, closed
ticket, third-party call — check whether it already happened:

1. Look in `[effects table]` for the row with
   `idempotency_key = "[run_id]:[unit]:[action]"`.
2. If it exists as `sent` or `succeeded`, copy the result and move on; if it
   is `in_progress`, do not fire it again.
3. If not, create it as `in_progress` before executing and update it when you
   finish.

On a timeout, a server error or a dropped connection, read the real state of the
resource before retrying.
```

## After repeated failures, escalate with the report

Every loop has an ending that is not success, and it has to be written. After [N] attempts or [T] minutes on the same unit, it stops trying. Without that number it keeps going when it is no longer useful and fails in silence: nobody notices until someone counts the effects.

Escalation needs a destination and a payload. Destination: a person or a channel. Payload: the unit, the literal error, the runs spent and what is missing. "Billing is failing" is useless; "invoice F-2231 has had five attempts, the last one with this text, and the customer has no payment method" is not. Notices: one message per clean run is noise; a daily digest hides the failure all day.

```text
Budget: at most [5] attempts on the same unit and [30] minutes from
`started_at`. On reaching either:

1. Stop. Do not take one more try "just in case".
2. Mark the unit `blocked` and set `loop_state.paused = true`.
3. Escalate to [person or channel] with this report, as plain text: the unit
   and what it means for the business; what was tried, with times; the last
   literal error; what is missing and which decision a person has to make.
4. Do not touch that unit again until someone unblocks it.

Report everything else only when the loop's state changes.
```

## What it never does unattended

Some actions are not handed to a process running at three in the morning: deleting data it did not create, moving money, changing prices, publishing, closing other people's tickets, touching production permissions or credentials. The list goes in the prompt, not in the head of whoever deployed it.

A loop also does not change its own prompt, its exit condition or its budget: if it thinks they should change, it writes that in the report and stops. A loop that redesigns itself every run wants the design of a goal. And a person's approval is data with an author, not an empty field read as permission.

```text
You do not do any of this in any run, with or without a later instruction in
the state:

- Delete or overwrite data you did not create in this run.
- Send money, change prices or touch contractual terms.
- Publish, answer a customer or close a ticket someone else opened.
- Change permissions, credentials or production configuration.
- Modify this prompt, the exit condition or the budget: if you think they
  should change, write it in the report and end the run.
- Execute a unit without having read the state from the previous run.

If a unit needs one of these actions, mark it `blocked` and say what is needed
in the report.
```

## When it misbehaves

| Symptom | Cause | Fix |
| --- | --- | --- |
| Sends the same email every morning | no processed marker, no effect check | idempotency key and a check before the action |
| Stops halfway and leaves no trace | state was written at the end | write it before replying |
| Twelve hours on the same error | no budget and no escalation target | an attempt cap and a report |
| Says "it's ready" when it is not | the exit condition is an impression | write it as a query against state |
| Does the work twice at once one day | two overlapping runs, no lock | per-unit lock |
| Invents an approval nobody gave | a "pending" field read as permission | approval with author and date |

## What changed, and when

- **1 November 2026.** This guide documents the `loop` typology in the skill catalogue. The coverage line is typed by hand: the skill describes a shape of prompt and declares no `models:` .
