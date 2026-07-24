# Contributing to HHVietSub

Thank you for helping improve HHVietSub. Contributions should be focused,
reproducible, and safe for users' subtitle, media, and CapCut project files.

## Before opening an issue

1. Search existing issues.
2. Reproduce the problem on the latest relevant branch.
3. Remove API keys, private subtitles, personal paths, and private media from
   screenshots and logs.
4. Include the application mode, Windows version, and exact steps needed to
   reproduce the problem.

Use the bug-report template for defects and the feature-request template for
new behavior.

## Development workflow

```powershell
git clone https://github.com/nguyenduchung98/HHVietSub.git
cd HHVietSub
git switch codex/lite
npm install
npm run dev
```

Create a focused branch, make the smallest practical change, and validate it:

```powershell
npm test
npm run build:web
```

Do not package or commit generated `dist`, runtime, cache, model, or user-data
directories.

## Pull requests

A pull request should:

- Explain the user-visible problem and solution.
- State whether it changes FFmpeg, CapCut, API, or job-state behavior.
- Include validation commands and results.
- Include before/after screenshots for interface changes.
- Add or update tests when behavior changes.
- Avoid unrelated formatting or dependency updates.

Changes to FFmpeg commands, CapCut draft structures, API credentials, or
destructive filesystem operations require extra review.

## Commit messages

Use concise messages such as:

- `fix: filter invalid CapCut project folders`
- `feat: add retry state to SRT queue`
- `docs: clarify FFmpeg setup`

## Security

Do not open public issues for vulnerabilities, exposed credentials, unsafe file
operations, or CapCut project corruption. Follow [SECURITY.md](SECURITY.md).
