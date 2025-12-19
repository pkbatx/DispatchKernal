#!/usr/bin/env python3
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import requests
from jsonschema import Draft7Validator
from openai import OpenAI

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"

ALLOWED_ENVS = {
    "TRANSCRIBE_BACKEND",
    "OPENAI_API_KEY",
    "OPENAI_STT_MODEL",
    "LOCALAI_STT_MODEL",
    "ANALYZE_BACKEND",
    "LOCALAI_BASE_URL",
    "LOCALAI_MODEL",
    "LOCALAI_TIMEOUT_S",
    "DEFAULT_TIMEZONE",
}


@dataclass
class Environment:
    transcribe_backend: str = "openai"
    analyze_backend: str = "localai"
    openai_api_key: Optional[str] = None
    openai_stt_model: str = "gpt-4o-transcribe"
    localai_stt_model: str = "whisper-1"
    localai_base_url: str = "http://localhost:8080"
    localai_model: str = "gpt-4o-mini"
    localai_timeout: int = 45
    default_timezone: str = "America/New_York"


class DKError(Exception):
    """Structured error for CLI failures."""


def emit_error(message: str, code: str = "error") -> None:
    payload = {"error": message, "code": code}
    sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.exit(1)


def load_environment() -> Environment:
    env = Environment()
    raw_env = {k: os.environ.get(k) for k in ALLOWED_ENVS}

    if raw_env.get("TRANSCRIBE_BACKEND"):
        env.transcribe_backend = raw_env["TRANSCRIBE_BACKEND"].strip().lower()
    if raw_env.get("ANALYZE_BACKEND"):
        env.analyze_backend = raw_env["ANALYZE_BACKEND"].strip().lower()
    if raw_env.get("OPENAI_API_KEY"):
        env.openai_api_key = raw_env["OPENAI_API_KEY"]
    if raw_env.get("OPENAI_STT_MODEL"):
        env.openai_stt_model = raw_env["OPENAI_STT_MODEL"]
    if raw_env.get("LOCALAI_STT_MODEL"):
        env.localai_stt_model = raw_env["LOCALAI_STT_MODEL"]
    if raw_env.get("LOCALAI_BASE_URL"):
        env.localai_base_url = raw_env["LOCALAI_BASE_URL"].rstrip("/")
    if raw_env.get("LOCALAI_MODEL"):
        env.localai_model = raw_env["LOCALAI_MODEL"]
    if raw_env.get("LOCALAI_TIMEOUT_S"):
        try:
            env.localai_timeout = int(raw_env["LOCALAI_TIMEOUT_S"])
        except ValueError:
            raise DKError("LOCALAI_TIMEOUT_S must be an integer")
    if raw_env.get("DEFAULT_TIMEZONE"):
        env.default_timezone = raw_env["DEFAULT_TIMEZONE"]
    return env


def ensure_file_exists(path: Path) -> None:
    if not path.exists() or not path.is_file():
        raise DKError(f"Input file not found: {path}")


def load_schema(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_payload(payload: Dict[str, Any], schema_name: str) -> None:
    schema_path = SCHEMAS_DIR / f"{schema_name}.schema.json"
    schema = load_schema(schema_path)
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        message = errors[0].message
        raise DKError(f"Schema validation failed for {schema_name}: {message}")


def strip_code_fences(text: str) -> str:
    fenced = re.sub(r"```[a-zA-Z]*", "", text)
    return fenced.replace("```", "").strip()


def extract_first_json(text: str) -> Dict[str, Any]:
    clean = strip_code_fences(text)
    start = clean.find("{")
    if start == -1:
        raise DKError("No JSON object found in model response")

    depth = 0
    collected: List[str] = []
    for char in clean[start:]:
        if char == "{":
            depth += 1
        if char == "}":
            depth -= 1
        collected.append(char)
        if depth == 0:
            break

    candidate = "".join(collected)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise DKError(f"Unable to parse JSON object: {exc}")


def transcribe_openai(audio_path: Path, env: Environment) -> Dict[str, Any]:
    if not env.openai_api_key:
        raise DKError("OPENAI_API_KEY is required for OpenAI transcription")

    client = OpenAI(api_key=env.openai_api_key)
    with audio_path.open("rb") as file_data:
        response = client.audio.transcriptions.create(
            model=env.openai_stt_model,
            file=file_data,
        )
    text = getattr(response, "text", None) or response.get("text")
    segments = getattr(response, "segments", None) or response.get("segments") or []
    return {
        "text": text or "",
        "language": getattr(response, "language", None) or response.get("language", ""),
        "confidence": None,
        "duration_s": None,
        "segments": segments,
    }


def transcribe_localai(audio_path: Path, env: Environment) -> Dict[str, Any]:
    url = f"{env.localai_base_url}/v1/audio/transcriptions"
    with audio_path.open("rb") as f:
        files = {"file": f}
        data = {"model": env.localai_stt_model}
        resp = requests.post(url, files=files, data=data, timeout=env.localai_timeout)
    if resp.status_code >= 400:
        raise DKError(f"LocalAI transcription failed: {resp.text}")
    payload = resp.json()
    return {
        "text": payload.get("text", ""),
        "language": payload.get("language", ""),
        "confidence": None,
        "duration_s": None,
        "segments": payload.get("segments") or [],
    }


def perform_transcription(audio_path: Path, env: Environment) -> Dict[str, Any]:
    ensure_file_exists(audio_path)
    if env.transcribe_backend == "openai":
        result = transcribe_openai(audio_path, env)
    elif env.transcribe_backend == "localai":
        result = transcribe_localai(audio_path, env)
    else:
        raise DKError(f"Unsupported TRANSCRIBE_BACKEND: {env.transcribe_backend}")

    # enforce segments array
    result.setdefault("segments", [])
    validate_transcription_payload(result)
    return result


def validate_transcription_payload(payload: Dict[str, Any]) -> None:
    required_fields = ["text", "language", "confidence", "duration_s", "segments"]
    for key in required_fields:
        if key not in payload:
            raise DKError(f"Transcription payload missing {key}")
    if not isinstance(payload.get("segments"), list):
        raise DKError("segments must be an array")


def build_metadata_stub(text: str, env: Environment) -> Dict[str, Any]:
    participants = []
    for marker in ["Agent", "Caller"]:
        pattern = rf"{marker} ([A-Z][a-zA-Z]+)"
        matches = re.findall(pattern, text)
        for match in matches:
            name = match.strip()
            if name not in participants:
                participants.append(name)

    time_match = re.search(r"(\d{1,2}:\d{2}\s?[APMapm]{2}\s?[A-Za-z/]*)", text)
    call_time = time_match.group(1).strip() if time_match else None

    issues = []
    if "checkout" in text.lower():
        issues.append("Checkout API timeouts")
    if "config change" in text.lower():
        issues.append("Recent config change")

    action_items = ["Send summary and next steps", "Monitor checkout stability"]
    summary = (
        "Caller reported checkout API timeouts impacting customers; rollback is stabilizing while monitoring continues."
    )
    sentiment = "neutral"

    return {
        "summary": summary,
        "participants": participants,
        "sentiment": sentiment,
        "call_datetime": call_time,
        "timezone": env.default_timezone,
        "action_items": action_items,
        "issues": issues,
    }


def build_rollup_stub(text: str, env: Environment) -> Dict[str, Any]:
    incidents = []
    if "checkout" in text.lower():
        incidents.append(
            {
                "type": "checkout-api",
                "description": "Checkout API is timing out for production customers",
                "severity": "high",
            }
        )
    if "config change" in text.lower():
        incidents.append(
            {
                "type": "config-change",
                "description": "Recent payment gateway config change correlated with incident",
                "severity": "medium",
            }
        )
    summary = "Intermittent checkout API failures; rollback underway and monitoring in place."
    next_steps = [
        "Confirm rollback completion",
        "Monitor error rates",
        "Share customer-facing summary",
    ]
    status = "monitoring"
    return {
        "summary": summary,
        "incidents": incidents,
        "next_steps": next_steps,
        "status": status,
    }


def call_localai_chat(prompt: str, text: str, env: Environment) -> Dict[str, Any]:
    url = f"{env.localai_base_url}/v1/chat/completions"
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": text},
    ]
    body = {
        "model": env.localai_model,
        "messages": messages,
        "temperature": 0,
    }
    resp = requests.post(url, json=body, timeout=env.localai_timeout)
    if resp.status_code >= 400:
        raise DKError(f"LocalAI analysis failed: {resp.text}")
    payload = resp.json()
    choices = payload.get("choices") or []
    if not choices:
        raise DKError("LocalAI response missing choices")
    content = choices[0].get("message", {}).get("content", "")
    return extract_first_json(content)


def perform_analysis(text: str, mode: str, env: Environment) -> Dict[str, Any]:
    mode = mode.lower()
    if mode not in {"metadata", "rollup"}:
        raise DKError(f"Unsupported analysis mode: {mode}")

    if env.analyze_backend == "stub":
        if mode == "metadata":
            result = build_metadata_stub(text, env)
            validate_payload(result, "metadata")
            return result
        result = build_rollup_stub(text, env)
        validate_payload(result, "rollup")
        return result

    if env.analyze_backend != "localai":
        raise DKError(f"Unsupported ANALYZE_BACKEND: {env.analyze_backend}")

    prompt = (
        "You are DispatchKernel. Extract a single JSON object only. Do not include prose or code fences. "
        "Validate against the provided schema."
    )
    raw_output = call_localai_chat(prompt, text, env)
    target_schema = "metadata" if mode == "metadata" else "rollup"
    validate_payload(raw_output, target_schema)
    return raw_output


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """DispatchKernel CLI."""
    ctx.ensure_object(dict)


@cli.command()
@click.option("--input", "input_path", required=True, type=click.Path(exists=False, dir_okay=False, path_type=Path))
@click.option("--out", "output_path", required=False, type=click.Path(dir_okay=False, path_type=Path))
def transcribe(input_path: Path, output_path: Optional[Path]) -> None:
    """Transcribe audio into JSON."""
    try:
        env = load_environment()
        result = perform_transcription(input_path, env)
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if output_path:
            output_path.write_text(output + "\n", encoding="utf-8")
        else:
            sys.stdout.write(output + "\n")
    except DKError as exc:
        emit_error(str(exc), code="transcribe_error")


@cli.command()
@click.option("--input", "input_path", required=True, type=click.Path(exists=False, dir_okay=False, path_type=Path))
@click.option("--mode", "mode", required=True, type=click.Choice(["metadata", "rollup"], case_sensitive=False))
def analyze(input_path: Path, mode: str) -> None:
    """Analyze transcript text into structured JSON."""
    try:
        env = load_environment()
        ensure_file_exists(input_path)
        text = input_path.read_text(encoding="utf-8")
        result = perform_analysis(text, mode, env)
        output = json.dumps(result, ensure_ascii=False, indent=2)
        sys.stdout.write(output + "\n")
    except DKError as exc:
        emit_error(str(exc), code="analysis_error")


@cli.command()
@click.option("--input", "input_path", required=True, type=click.Path(exists=False, dir_okay=False, path_type=Path))
@click.option("--mode", "mode", required=True, type=click.Choice(["both"], case_sensitive=False))
def pipeline(input_path: Path, mode: str) -> None:
    """Compose transcription and analysis."""
    try:
        env = load_environment()
        transcription = perform_transcription(input_path, env)
        text = transcription.get("text", "")
        metadata = perform_analysis(text, "metadata", env)
        rollup = perform_analysis(text, "rollup", env)
        payload = {
            "transcription": transcription,
            "metadata": metadata,
            "rollup": rollup,
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2)
        sys.stdout.write(output + "\n")
    except DKError as exc:
        emit_error(str(exc), code="pipeline_error")


if __name__ == "__main__":
    cli()
