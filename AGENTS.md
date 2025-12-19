DispatchKernel — AGENTS.md

Purpose

DispatchKernel is a standalone, command-line kernel that converts:
	1.	Audio → Transcript (speech-to-text)
	2.	Transcript → Structured Intelligence (metadata + rollups)

It is designed to be embedded into larger systems while remaining isolated, testable, and side-effect free.

⸻

Core Operating Principles (non-negotiable)
	1.	Isolation
	•	No databases
	•	No HTTP servers
	•	No background workers
	•	No alerts, notifications, or messaging
	•	No UI
	2.	Read-Only Intelligence
	•	This project never triggers actions
	•	Output is informational only
	•	Language must remain observational, not directive
	3.	Deterministic Boundaries
	•	Inputs are explicit (audio or text)
	•	Outputs are strict JSON only
	•	All outputs validate against JSON Schema
	•	Fail fast on invalid output
	4.	CLI-First
	•	Everything runs from the command line
	•	No daemon mode
	•	No hidden state
	•	No implicit configuration
	5.	Docker-Friendly
	•	LocalAI is run via Docker
	•	CLI runs natively on host
	•	No assumption of root or writable filesystem outside working directory

⸻

Supported Capabilities

1) Transcription (Speech → Text)

Primary backend:
	•	OpenAI GPT-4o Speech-to-Text

Secondary backend:
	•	LocalAI Whisper-compatible API

Rules:
	•	Transcription and analysis are independent
	•	Transcription must not invoke analysis automatically
	•	Output must include a segments array (empty allowed)

⸻

2) Analysis (Text → JSON)

Supported analysis modes:
	•	metadata
	•	rollup
	•	both

Rules:
	•	Analysis operates only on text
	•	No audio access during analysis
	•	Output must be one JSON object only
	•	No markdown, no prose, no commentary

⸻

CLI Contract (Frozen)

Single entrypoint: tools/dk.py

Valid commands:

dk transcribe --input call.mp3 --out transcript.json
dk analyze    --input transcript.txt --mode metadata
dk analyze    --input transcript.txt --mode rollup
dk pipeline   --input call.mp3 --mode both

Rules:
	•	transcribe never performs analysis
	•	analyze never touches audio
	•	pipeline is explicit composition only
	•	Any failure:
	•	non-zero exit code
	•	machine-readable JSON error to stderr

⸻

Output Rules

Transcription Output
	•	Must always include:
	•	text
	•	segments (array, empty allowed)
	•	Confidence may be null
	•	Duration may be null
	•	Never partially emit output

Analysis Output
	•	Must validate against schema
	•	Must not invent fields
	•	Unknown values must be null, empty string, or empty array (per schema)
	•	Must not include operational instructions

⸻

Model Interaction Rules
	•	Do not trust model output
	•	Always:
	•	strip code fences
	•	extract first JSON object
	•	validate against schema
	•	No streaming
	•	No speculative retries
	•	At most one retry for transient network failure

⸻

Environment Variables (Explicit Only)

Allowed environment variables:
	•	TRANSCRIBE_BACKEND
	•	OPENAI_API_KEY
	•	OPENAI_STT_MODEL
	•	LOCALAI_STT_MODEL
	•	ANALYZE_BACKEND
	•	LOCALAI_BASE_URL
	•	LOCALAI_MODEL
	•	LOCALAI_TIMEOUT_S
	•	DEFAULT_TIMEZONE

Do not read or depend on any others.

⸻

Prohibited Behavior (Hard Rules)

This project must never:
	•	Send alerts
	•	Send messages
	•	Write to databases
	•	Start servers
	•	Spawn background workers
	•	Perform automatic downstream actions
	•	Modify external systems
	•	Expose secrets
	•	Log raw audio or transcripts by default

Any change violating these rules is invalid.

⸻

Testing Expectations
	•	Tests must run without:
	•	OpenAI access
	•	LocalAI running
	•	Tests validate:
	•	Schema compliance
	•	CLI behavior
	•	Failure modes
	•	Golden fixtures are preferred

⸻

Change Workflow

When modifying behavior:
	1.	Update or extend schema (prefer additive changes)
	2.	Update prompt logic and validation
	3.	Add or update fixtures
	4.	Add or update tests
	5.	Verify CLI commands still match contract

Avoid refactors unless required.

⸻

Acceptance Checklist (Required)

Before considering work complete:
	•	CLI runs locally with sample input
	•	Output validates against schema
	•	Invalid model output fails loudly
	•	Docker Compose starts LocalAI cleanly
	•	No new commands were added
	•	No side effects introduced

⸻

Mental Model

Treat DispatchKernel as a pure function boundary:

input → validate → transform → validate → output

If a proposed change breaks that model, it does not belong in this repository.

