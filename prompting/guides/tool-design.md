---
disabled: true
---

# Tool design for agents: the description decides the call

**Source:** [https://systempromptmaster.com/learning/tool-design](https://systempromptmaster.com/learning/tool-design)
**Downloaded:** 2026-11-10

**Description:** How to write a tool definition an agent uses well: the description that decides selection, the verb_object name and parameters with a type and a unit.

> **Quick answer:** Write the description so it answers what the tool does, when to use it and when not to, name each tool verb_object, declare every parameter with a type and a unit, tag whatever writes as irreversible, and return errors that separate what can be fixed from what cannot.

A tool is the part of the prompt that runs. The model never reads your documentation: it reads a name, a description, a schema, and the lines you wrote about the order calls go in. That is what it decides on, every turn.

So a bad tool gets fixed in two places: the definition, which the model always sees, and the prompt, the only place where the route between calls and the recovery rule can live. Nothing here names a vendor field. The format moves; the content does not.

## The description is the prompt read at every decision

The schema declares the shape of the call; the description declares what the tool is for. When choosing, the model reads the name and the description; it consults the schema only to fill the arguments. A description that restates the name adds nothing: "sends an email" never says when.

It earns its place when it answers four questions in order: what it does, when to use it, when not to, and what it returns. The first goes with the real object and its limits: "the customer's open orders, newest first, at most twenty" beats "queries orders". The second and third name the neighbouring tool, and that is what prevents the wrong call.

One tool, one responsibility. `search_orders` and `refund_order` are two tools; a `manage_order` that searches, refunds or cancels on an argument is three tools in a trench coat. When two overlap — `get_customer` against `lookup_user` — the model hesitates on every call: merge them, or state the difference in both. If the prompt is the only place the tools exist, define them in full; if they already exist, a short contract is enough, and it must never contradict them.

```text
search_orders
  What it does: the customer's open orders, newest first, at most 20.
    Each order carries order_id, status and total.
  When to use it: order history, and the status of one order.
  When not to: shipment tracking, which has track_shipment.
  Returns: a list of orders, or [] when none are open.
```

## The name carries the verb and the object

`verb_object`, lowercase, no cleverness: `create_invoice`, `fetch_weather`, `send_email`. The name says what happens and to what, and it is the first selection cue.

Two things break a name: vagueness, and looking like another name. `process`, `handle` and `manage` say nothing; `pg_query` names the implementation; and two near-identical names for different behaviours — `delete_file` and `remove_file` — force the whole description to be read every time, which is what the name saved you. If two tools differ by scope, differ by the same axis: `list_tickets` and `update_ticket`, not `tickets` and `modify`.

```text
verb_object, lowercase: search_orders, refund_order, send_email.
Banned: process, handle, manage, and any name that needs a sentence to
explain itself.
```

## Every parameter states a type, a unit, and what missing looks like

A parameter without a unit is one bad call waiting: `timeout` invites seconds where the API expects milliseconds, and `amount` invites euros where the system counts cents. Each one carries type, meaning and constraint: required or optional, allowed values, default, unit, format.

A few well-named parameters beat one free-form blob: a text `payload` hides the shape and hands the model a guess you had already solved. If a parameter takes several forms, list them: "`period`: `day`, `week` or `month`" gets answered correctly; "`period`: the period" does not. Where the format matters, put the example in, and validate server-side: a schema is not a business rule.

```text
refund_order
  order_id      string, required. The order_id search_orders returned.
  amount_cents  integer, required, in cents. No decimals.
  reason        string, required. One of: damaged, not_received, wrong_item.
  restock       boolean, optional, defaults to true.
```

## What comes back decides the next call

A tool's return is the input to the next decision, so it deserves the care you gave the prompt's input. Return the fields the model needs, with names that hold across calls, units attached to the number, and nulls explicit: a field that sometimes goes missing gets read as zero. And return little: an unbounded dump buries the signal and makes every later turn more expensive. If the model needs more, let it ask with an argument.

Errors are the other half of the contract. Each carries a code, a message and whether the call changed anything, in one of three classes, each demanding its own reaction: what the model can fix, what it cannot — permission denied, missing resource — and what is not an error — an empty list. Without that distinction everything is "error", and the model cannot tell a retry from a change of approach.

The recovery rule belongs in the prompt, not the tool, plus one prohibition: never let it answer as though the call had succeeded.

```text
Tool errors, three classes, one reaction each:
- fixable (bad argument): correct the argument and retry once.
- transient (timeout, rate limit): wait and retry once.
- permanent (no permission, does not exist): do not retry; say what is missing.
An empty list is not an error: it is "no results".
Never answer as though the call had succeeded.
```

## Before you switch a tool on, check whether it reads or writes

Every tool carries an effect tag: read-only, idempotent write, or non-idempotent side effect. That tag decides whether a retry is free. A read repeats at no cost; a write that sets a value repeats harmlessly; a send, a charge or a publish does not.

The third kind needs an idempotency key or a check-before-act, and a confirmation of intent before it runs. The description says what is irreversible and what the safe alternative is: the model needs that while choosing, not after. And a tool that both reads and writes is harder to reason about and to retry: split it.

```text
Effect, in each tool description:
- read-only: retry freely.
- idempotent write: repeating the same value changes nothing.
- non-idempotent effect: send, charge, publish. Requires idempotency_key
  and a confirmation of intent.

Before a non-idempotent tool, state in one line what you are about to do.
If the identifier or amount is missing, do not call it.
```

## How many tools at once

Every added tool makes the choice harder. Keep the set to what the work needs — often fewer than ten active — and group what grows by job, saying which applies to which request. When the catalog is large, the answer is not to expose all of it: it is a discovery tool that returns the three or four that apply.

For a simple need the problem is selection; for a compound one it is chaining: order the calls and pass each result along. When the route is known, write it; when it is not, write the stopping rule. In parallel, only independent reads.

```text
Known route:
1. search_orders for the customer.
2. For each open order, get_shipment with its order_id.
3. If there are no open orders, stop: do not look for shipments.

Stopping rule: keep going until the question can be answered, not until the
calls run out. Never fire two calls in parallel when the second needs a value
from the first.
```

## When it calls the wrong tool

The first instinct is to add another tool, and it is almost always the worst move: it grows the catalog and leaves the cause alone. Before adding anything, read what the model reads.

Four checks, in order. Does the first line of the description, on its own, separate this tool from its neighbour? Are two overlapping, with neither saying how? Does the name carry the action, or does it take a paragraph? Did the request need a chain, and you exposed the steps loose, without order?

If it picks the right tool and gets the arguments wrong, the parameter is the problem: a missing unit, allowed value or example. If it writes when a read would have done, the effect tag is not in the prompt. And a request with no tool to serve it gets written into the prompt as an exit, not as one more tool.

```text
If no available tool serves the request, do not force the closest one: say
what is needed and stop.
If two tools could serve, pick the read-only one and explain in one line why
you did not use the other.
```

## When it misbehaves

| Symptom | Cause | Fix |
| --- | --- | --- |
| Always calls the same tool, needed or not | its description never says when to use it | write "when to use" naming the other tool |
| Fills a parameter with the wrong unit | the unit is undeclared | add unit, example and range |
| Retries a charge three times | the effect is untagged | tag it non-idempotent and require a key |
| Answers "done" when the call failed | the prompt does not forbid it | add the prohibition and the error code |

## What changed, and when

- **1 November 2026.** Publication of this guide. It cites no sources because it depends on no vendor: everything here is written into the name, the description, the schema and the prompt.
