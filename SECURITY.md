# Security Policy

## Supported versions

Security fixes are applied to the latest maintained branch and release. Older
development snapshots may not receive fixes.

## Reporting a vulnerability

Do not disclose vulnerabilities or credentials in a public issue.

Use GitHub's private vulnerability reporting feature for this repository. If
private reporting is not available, contact the repository owner through the
public contact method on the GitHub profile and request a private reporting
channel. Do not include secrets or private user data in the initial message.

Please include:

- Affected branch, version, or commit.
- Reproduction steps or a minimal proof of concept.
- Expected impact.
- Whether API keys, local files, CapCut projects, or remote requests are
  involved.
- Suggested mitigation, if known.

The maintainer will acknowledge a valid report when possible, investigate it,
and coordinate disclosure after a fix is available.

## Security-sensitive areas

- Windows secret storage and API-key handling
- Remote TTS requests and downloaded audio
- File and folder selection
- FFmpeg process execution
- CapCut project backup and JSON modification
- Job recovery after cancellation or application restart
