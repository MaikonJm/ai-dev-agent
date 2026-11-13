# ADR 0002: A hand-written agent loop instead of a framework

- **Status:** accepted
- **Date:** 2026-11-12

## Context

Frameworks (LangGraph, CrewAI, Strands, Bedrock Agents) speed up prototypes but hide the control flow that safety depends on: which tools exist in each phase, when the budget is checked, what happens on a malformed answer.

## Decision

A small loop on the Bedrock Converse API (`agent/loop.py`, about 100 lines). Tools are plain Python with explicit limits (`agent/tools.py`). Git, PRs and comments are done by orchestration code, never by the model.

## Consequences

- Every step is visible and unit-tested with a scripted fake model.
- The plan phase gets read-only tools, and the loop refuses writes even if the model asks.
- Swapping models is a configuration change; a framework can still be evaluated later against the same eval suite.
