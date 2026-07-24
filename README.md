# HHVietSub

HHVietSub is an open-source Windows desktop application for Vietnamese subtitle
and video-production workflows. It combines an Electron + React interface with a
Python worker to turn SRT subtitles into speech, synchronize video to generated
voice tracks with FFmpeg, and safely update existing CapCut projects.

The repository contains the full application and the lightweight
`codex/lite` edition. HHVietSub Lite focuses on low-resource computers and keeps
the core CapCut TTS, SRT queue, pronunciation dictionary, FFmpeg sync, and
existing-project CapCut workflows.

## Why this project exists

Vietnamese creators often need to combine several unrelated tools to translate
or prepare subtitles, generate speech, repair pronunciation, synchronize video,
and update an editor project. HHVietSub brings those operations into one
maintainable desktop workflow while keeping source files and job state visible
to the user.

## HHVietSub Lite features

- Process one SRT file or queue every SRT file in a folder.
- Generate speech through CapCut TTS, AI33, or AIMax integrations.
- Maintain an importable and exportable pronunciation dictionary.
- Retry failed subtitle lines without restarting the whole job.
- Synchronize video timing to voice files through FFmpeg.
- Use machine profiles for low-resource, balanced, or faster rendering.
- Back up and update existing CapCut projects.
- Keep the Lite installer free of local GPU models and heavyweight AI runtimes.

## Architecture

| Area | Technology |
| --- | --- |
| Desktop shell | Electron |
| User interface | React, TypeScript, Vite |
| Worker | Python |
| Media processing | FFmpeg and FFprobe |
| Local data | App-specific user-data directory |

Frontend-to-worker calls use a small RPC boundary. Long-running SRT and media
jobs report progress back to the interface and retain per-line state so failed
work can be retried.

## Requirements

- Windows 10 or Windows 11
- Node.js 22 or later
- npm 10 or later
- Python 3.12 or later
- FFmpeg and FFprobe available in `PATH` for synchronization features

Some CapCut workflows require an existing local CapCut installation and a
separately configured CapCut bridge. Remote TTS providers may require API keys
or send subtitle text to third-party services. Do not use remote providers for
confidential content unless you understand and accept their privacy terms.

## Development setup

```powershell
git clone https://github.com/nguyenduchung98/HHVietSub.git
cd HHVietSub
git switch codex/lite
npm install
npm run dev
```

To choose the Python executable explicitly:

```powershell
$env:DCC_PYTHON = "C:\Python312\python.exe"
npm run dev
```

The development command starts Vite, compiles Electron in watch mode, and opens
the desktop application. Windows packaging is intentionally separate:

```powershell
npm run package:win
```

## Validation

Run the complete Lite validation suite:

```powershell
npm test
```

Useful focused checks:

```powershell
npm run typecheck
npm run build:web
npm run test:backend
npm run backend:check
```

## Privacy and security

- API keys are stored through the application's Windows-backed secret storage.
- Local SRT, audio, video, and CapCut files remain on the user's computer unless
  the selected TTS provider requires remote processing.
- Security issues should be reported privately as described in
  [SECURITY.md](SECURITY.md), not posted as public issues.

## Contributing

Bug reports, reproducible test cases, documentation improvements, and focused
pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## Project status

HHVietSub is under active development. Interfaces and external TTS integrations
may change as upstream services evolve. Releases should document breaking
changes and include the validation results used before publishing.

## License

HHVietSub is released under the [MIT License](LICENSE). Third-party components
inside `vendor/` retain their own licenses.
