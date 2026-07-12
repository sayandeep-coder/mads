RESEARCH_PROMPT_TEMPLATE = """\
Research mode: "{topic}"

Research this topic thoroughly using all of these sources — call them \
together in this turn rather than one at a time, since they're independent \
lookups:

- Context7: official documentation for the topic (resolve the library/\
project first if needed)
- GitHub: real-world code examples, notable repositories, how the \
community actually uses this in production
- Fetch: broader web context — the official site, key articles, anything \
Context7/GitHub don't cover
- YouTube: conference talks, deep-dive videos, expert commentary on the \
topic

Once you have results back, synthesize everything into a structured \
executive report, written the way a VP Engineering would want it — clear, \
dense, no fluff:

# {topic}: Executive Research Report

## Executive Summary
2-3 sentences: what it is, why it matters, bottom line.

## Official Documentation
What the docs say — core concepts, how it's meant to be used.

## Real-World Implementations
What GitHub shows — notable projects, common patterns, maturity of the \
ecosystem.

## Community & Expert Perspective
What the broader web and video sources add — context, debates, gotchas \
docs don't mention.

## Risks & Open Questions
Anything unresolved, immature, or worth being cautious about.

## Recommendation
A clear, direct call: adopt, evaluate further, or avoid — and why.

Keep the report itself clean and professional — no Hinglish or casual \
tone inside the report body, that's for the conversation around it, not \
the deliverable.
"""


def build_research_prompt(topic: str) -> str:
    return RESEARCH_PROMPT_TEMPLATE.format(topic=topic)
