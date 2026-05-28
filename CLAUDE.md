# Agent Workflow

All development requests in this repository should follow the two-agent workflow defined in [docs/agent-workflow.md](docs/agent-workflow.md).

## Agents

1. Development Agent
   Implements the requested change, records assumptions, and proposes verification targets.
2. Verification Agent
   Reviews the change independently for regressions, missing tests, edge cases, and requirement mismatches.

## Rule

Do not treat a development task as complete until both agents have done their part and any findings have been addressed or explicitly called out.
