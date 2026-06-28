# Security Policy

## Supported Versions

We currently support security fixes for the latest release line on `main`.

| Version | Supported |
| ------- | --------- |
| `1.6.x` | Yes |
| `<1.6.0` | No |

If you are running an older version, please upgrade before reporting a
security issue unless the problem prevents upgrade.

## Reporting a Vulnerability

Please do not open a public GitHub issue for unpatched security bugs.

Instead, report vulnerabilities by email:

- `ankithemantlade+agentarmor-security@gmail.com`

Include as much of the following as you can:

- affected version or commit
- reproduction steps or proof of concept
- attack preconditions
- expected impact
- suggested remediation, if known

If the issue involves secrets, credentials, or customer data, redact them
before sending.

## Response Expectations

We aim to:

- acknowledge new reports within 3 business days
- provide an initial triage update within 7 business days
- coordinate a fix and disclosure timeline for valid reports

Complex reports may take longer to investigate, especially if they depend on
upstream provider SDK behavior.

## Disclosure Process

For confirmed vulnerabilities, we will try to:

1. reproduce and scope the issue
2. prepare a patch
3. coordinate disclosure timing with the reporter when appropriate
4. publish a fix and release notes

Please avoid public disclosure until a fix or mitigation is available, unless
we mutually agree on a different process.

## Scope Notes

AgentArmor is a local-first Python runtime safety layer. Reports are most
useful when they involve:

- bypasses in runtime safety modules
- unsafe provider patching behavior
- policy enforcement failures
- sensitive data leakage caused by AgentArmor itself
- integrity issues in audit, tracing, or approval paths

False positives, feature requests, or example/docs issues should go through
the normal GitHub issue tracker instead.
