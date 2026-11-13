# Evaluations

Five known tasks run through the real pipeline (issue → plan → `/approve` → PR). Each PR is then
checked out and scored with an acceptance test the agent never saw. Results are committed in
`results/<date>.json`, so every change to prompts, tools or models is measured the same way.

| Case | Kind |
| --- | --- |
| cart-total-quantity | bug fix |
| search-tests | tests only |
| delete-cart-item | small feature |
| quantity-validation | input validation |
| refactor-cart-store | refactor with tests |

```bash
export GITHUB_TOKEN=...   # fine-grained, sandbox repo only: Issues + Contents read/write
python -m evals.run_evals --only cart-total-quantity
```
