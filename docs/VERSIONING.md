# Versioning

Use Git tags to mark MVP releases, staging cuts, and rollback points.

## Tag Format

Recommended release tag formats:

- `v0.1.0-mvp.1` for MVP release candidates or early operator releases.
- `v0.1.0` for the first accepted MVP baseline.
- `v0.1.1` for compatible fixes.
- `v0.2.0` for larger workflow or API additions.

Use annotated tags for shared releases:

```bash
git tag -a v0.1.0-mvp.1 -m "MVP private workflow release"
git push origin v0.1.0-mvp.1
```

Avoid moving a published tag. Create a new patch or release-candidate tag instead.

## Pre-Tag Checklist

Before tagging:

1. Confirm `main` is clean and pushed.
2. Confirm branch protection checks passed.
3. Run the validation listed in `docs/status.md`.
4. Complete `docs/RELEASE_READINESS.md`.
5. Fill out `docs/RELEASE_NOTES_TEMPLATE.md`.
6. Confirm no media, outputs, local databases, `.env` files, or credentials are present.
7. Confirm release notes state that outputs remain private and manual-upload only.

## Release Notes

Create release notes from `docs/RELEASE_NOTES_TEMPLATE.md` and include:

- tag
- commit SHA
- CI run link
- smoke evidence
- configuration changes
- private media/output handling confirmation
- known gaps and accepted risks

## Rollback References

For every release tag, record:

- previous known-good tag
- migration rollback notes
- deployment rollback steps
- any manual cleanup required for staged or delivered outputs

Do not delete delivered private output artifacts during rollback unless the retention policy says they are due and the project owner has confirmed manual upload status.
