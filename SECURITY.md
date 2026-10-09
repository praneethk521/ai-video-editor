# Security Policy

## Supported Versions

Security fixes are applied to the current `main` branch. This project has not published a stable production release yet.

## Reporting a Vulnerability

Do not open a public issue for a suspected vulnerability or include secrets, private media, access tokens, private locators, or customer data in a report.

Use this repository's **Security** tab to submit a private vulnerability report.
If private reporting is unavailable, use the maintainer's private contact method
and include only the minimum details needed to establish contact.

Reports should include the affected component, impact, reproduction steps, and suggested mitigation when available. You can expect an initial acknowledgement within five business days. No production data or credentials are required to reproduce a report; use synthetic media and test-only tokens.

## Scope

In scope:

- Authentication, authorization, project isolation, and service-token boundaries.
- Exposure of private source media, rendered outputs, OAuth credentials, or private locators.
- Path traversal, command injection, SSRF, unsafe media handling, and worker isolation failures.
- Dependency or CI supply-chain weaknesses that can affect released artifacts.

Out of scope:

- Social engineering, denial of service against third-party providers, and attacks requiring stolen user credentials without a product defect.
- Reports based only on automated scanner output without a reproducible impact.
- Public test data or documentation examples that contain no real secrets or private media.
