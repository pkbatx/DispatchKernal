# DispatchKernel

DispatchKernel is a CLI-only kernel for converting calls into structured intelligence. It provides
transcription and analysis commands designed to be deterministic, testable, and side-effect free.

## Features
- **Transcription** via OpenAI GPT-4o Speech-to-Text or a LocalAI Whisper-compatible endpoint.
- **Analysis** that produces strict JSON for metadata extraction and incident rollup summaries,
  validated against JSON Schema.
- **Pipeline** command to combine transcription and analysis in one invocation.

## Repository structure
```
DispatchKernel/
├── AGENTS.md
├── README.md
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── tools/
│   └── dk.py
├── schemas/
│   ├── metadata.schema.json
│   └── rollup.schema.json
├── fixtures/
│   └── sample_transcript.txt
└── tests/
    └── test_cli.py
```

## Installation
1. Create and activate a Python 3.10+ virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Environment variables
The CLI reads only the following variables (defaults shown where applicable):

```
# Transcription
TRANSCRIBE_BACKEND=openai        # openai | localai
OPENAI_API_KEY=
OPENAI_STT_MODEL=gpt-4o-transcribe
LOCALAI_STT_MODEL=whisper-1

# Analysis
ANALYZE_BACKEND=localai          # localai | stub
LOCALAI_BASE_URL=http://localhost:8080
LOCALAI_MODEL=gpt-4o-mini
LOCALAI_TIMEOUT_S=45
DEFAULT_TIMEZONE=America/New_York
```

## Usage

The CLI entrypoint is `tools/dk.py`. Run commands with Python:

```bash
python tools/dk.py transcribe --input call.mp3 --out transcript.json
python tools/dk.py analyze --input transcript.txt --mode metadata
python tools/dk.py analyze --input transcript.txt --mode rollup
python tools/dk.py pipeline --input call.mp3 --mode both
```

### Transcription
- Does **not** perform analysis.
- Produces a strict JSON object with `text`, `language`, `confidence`, `duration_s`, and `segments`.
- When `TRANSCRIBE_BACKEND=openai`, an `OPENAI_API_KEY` is required.
- When `TRANSCRIBE_BACKEND=localai`, requests are sent to the LocalAI Whisper-compatible endpoint
  defined by `LOCALAI_BASE_URL`.

### Analysis
- Operates only on transcript text. It never accesses audio files.
- Supports `metadata` and `rollup` modes. Each output validates against the schema in
  `schemas/`.
- By default, analysis uses LocalAI (`ANALYZE_BACKEND=localai`). Set `LOCALAI_BASE_URL` and
  `LOCALAI_MODEL` to point at your LocalAI deployment. For deterministic, offline runs you can set
  `ANALYZE_BACKEND=stub`, which uses a rule-based extractor suitable for tests and development
  without network access.

### Pipeline
- Explicitly composes transcription followed by analysis in one command when `--mode both`.
- Output is a single JSON object containing `transcription`, `metadata`, and `rollup` fields.

## Docker (LocalAI)
Run LocalAI for development with Docker Compose:

```bash
docker compose up
```

The compose file starts a single LocalAI service bound to port `8080` with a readiness probe on
`/readyz`.

## Testing
Run the test suite with pytest:

```bash
pytest
```

Tests run fully offline by exercising the stub analysis backend and validating outputs against the
JSON Schemas.

## Failure modes
- On any failure, commands exit non-zero and emit a machine-readable JSON error to stderr.
- Outputs are never streamed and are emitted only after validation succeeds.

