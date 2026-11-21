# Scheduling repair pilot

This small Python project contains three independent defects and five passing baseline tests. It has no third-party dependencies. Copy this folder outside the FixForge checkout, initialize Git there, commit the baseline, and register the folder in `FIXFORGE_REPOSITORIES` using an absolute path. Start from the same baseline for each issue so every run has its own source evidence.

| Issue title | Description to enter in FixForge |
|---|---|
| Back-to-back meetings conflict | `slots_overlap((10, 20), (20, 30))` returns true. Half-open intervals that touch at an endpoint should not overlap. Keep the results for genuinely intersecting and separated intervals. |
| Billing rounds exact multiples up again | `billable_minutes(30, 15)` returns 45. Exact multiples should stay unchanged, zero minutes should return zero, and partial increments should still round up. Keep input validation. |
| Guest list retains case-only duplicates | `unique_guests(["Ada@example.com", "ada@example.com", "Bo@example.com"])` should return `["Ada@example.com", "Bo@example.com"]`. Compare addresses case-insensitively, preserving the first original spelling and input order. |

Once Docker and an API key are available, run each issue through **New repair → AI repository repair**. Record the model, token usage, source commit, image ID, gate results and reviewer decision. These authored cases are for validating the pilot workflow.
