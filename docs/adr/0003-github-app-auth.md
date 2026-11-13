# ADR 0003: GitHub App instead of a personal token

- **Status:** accepted
- **Date:** 2026-11-12

## Context

The agent comments on issues, pushes branches and opens pull requests. A personal access token would act as the owner, across repositories, for months.

## Decision

A GitHub App installed only on the sandbox repository, with permissions limited to contents, issues and pull requests. The runner exchanges a short-lived JWT for an installation token that expires in one hour. The private key and the webhook secret live in SSM Parameter Store (SecureString), set in the console.

## Consequences

- Actions show up as the app, not as a person, and stop working as soon as the app is uninstalled.
- `main` is protected by branch protection; the agent pushes only to `agent/issue-<n>` and cannot merge.
- Setup needs a few manual steps in the GitHub UI, listed in the runbook.
