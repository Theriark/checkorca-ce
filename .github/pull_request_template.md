## Summary

<!-- One change, one outcome. Link the task or Jira issue. -->

## Checklist

- [ ] Branch is `feat/checkorca-ce-<task or topic>` and the pull request targets `development`
- [ ] CI `Merge gate summary` is green on the head commit; a skipped check is not a pass
- [ ] Tests added or updated for the behaviour changed
- [ ] No secrets, credentials or real client data committed; test data is synthetic and labelled
- [ ] New dependencies are pinned and on the licence allow-list (docs/ci-cd.md)
- [ ] No EE code or EE package reference in CE
- [ ] Documentation updated where behaviour or workflow changed
- [ ] Reviewed by someone other than the author

## Evidence

<!-- Commit SHA, CI run id, test output summary, screenshots at 1440, 768 and 390 for UI changes. -->
