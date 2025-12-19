import json
import os
import subprocess
import sys
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = {
    "metadata": json.load((REPO_ROOT / "schemas" / "metadata.schema.json").open()),
    "rollup": json.load((REPO_ROOT / "schemas" / "rollup.schema.json").open()),
}


def run_cli(args):
    env = os.environ.copy()
    env["ANALYZE_BACKEND"] = "stub"
    cmd = [sys.executable, str(REPO_ROOT / "tools" / "dk.py")] + args
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def validate_schema(payload, name):
    jsonschema.validate(instance=payload, schema=SCHEMAS[name])


def test_analyze_metadata_stub():
    transcript = REPO_ROOT / "fixtures" / "sample_transcript.txt"
    result = run_cli(["analyze", "--input", str(transcript), "--mode", "metadata"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    validate_schema(payload, "metadata")


def test_analyze_rollup_stub():
    transcript = REPO_ROOT / "fixtures" / "sample_transcript.txt"
    result = run_cli(["analyze", "--input", str(transcript), "--mode", "rollup"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    validate_schema(payload, "rollup")


def test_invalid_file_errors():
    missing = REPO_ROOT / "fixtures" / "missing.txt"
    result = run_cli(["analyze", "--input", str(missing), "--mode", "metadata"])
    assert result.returncode != 0
    assert result.stderr.strip().startswith("{")
