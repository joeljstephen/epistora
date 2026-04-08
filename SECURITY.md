# Security Policy

## Supported use

Epistora is designed for local-first or otherwise trusted deployments. If you
expose the FastAPI server beyond localhost, enable bearer auth and review the
network posture of the machine hosting the worker, vault, and database.

## Reporting a vulnerability

Please report suspected security issues privately to the maintainers before
opening a public issue. Include:

- affected version or commit
- reproduction steps
- impact assessment
- any suggested mitigation

If a private contact path is not available, open a minimal public issue without
exploit details and request a secure follow-up channel.

## Current protections

- Optional API auth: when `EPISTORA_API_KEY` is set, sensitive API routes
  require `Authorization: Bearer <token>`.
- SSRF guardrails: user-supplied ingest URLs are limited to `http` and `https`
  and blocked for localhost, link-local, RFC1918/private, metadata-service, and
  other non-public IP ranges.
- Redirect checks: article, generic, and PDF fetchers re-validate the final URL
  after HTTP redirects.

## Known limitations

- DNS rebinding is only partially mitigated. Hostnames are resolved before the
  request and validated again after redirects, but an attacker controlling DNS
  can still create time-of-check/time-of-use races.
- Browser-based fallbacks and third-party fetch integrations depend on external
  tools and services that may have their own security properties.
- `/health` remains intentionally unauthenticated so operators can use it for
  basic liveness checks.

## Recommended deployment posture

- Bind the API to localhost unless remote access is required.
- Set a strong `EPISTORA_API_KEY` before exposing the API on any shared network.
- Run the worker and API with filesystem permissions scoped to the vault and app
  data they actually need.
- Keep CLI dependencies such as `opencode`, `claude`, and Playwright updated.
