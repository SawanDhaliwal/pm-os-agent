---
name: explain-like-a-pm
description: Explain a code change, diff, PR or commit in plain English for a product manager, and point out the engineering idea worth learning from it. Use when the user asks what a change does, to explain a PR or diff, or "what did you just do".
---

# Explain a change like I'm a PM

The reader is a product leader who is learning engineering. They want the product meaning first and the engineering idea second.

## Shape of the answer

1. **What changed for the user**, in two or three sentences. No code words unless you define them.
2. **How it works**, as a short walk through the pieces that changed: which file does what, in everyday terms.
   Use an analogy only if it is accurate.
3. **Risk and trade-offs**: what could break, what was chosen over what, and what it costs (speed, money, complexity).
4. **One thing to learn**: name the engineering concept this change shows (for example "fail soft", "dependency injection",
   "idempotent jobs", "test fixtures"), explain it in a paragraph from first principles, and say where else it shows up.
5. **Try it yourself**: one command or small edit the reader could make to see the idea in action.

Keep it under about 400 words unless asked for more. Get the diff with `git diff` or `git show` if you don't have it.
