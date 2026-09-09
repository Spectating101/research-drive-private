# Synthesis frozen method export — freeze checkpoint

Non-functional audit marker for the final Synthesis reproducibility closure.

Product tree immediately below this marker: `6901f5edbdc69e7f3c649be7200647d81200b367`.

The completed execution now freezes `method.py` beside `output.parquet` and `manifest.json` and records its SHA-256, accepted execution-spec hash, and method-origin metadata. The method proposal is recorded through the Composer `research_synthesis_propose_state` tool, researcher acceptance binds the exact proposal/spec revision, and script generation is deterministic from that accepted spec. Viewing or downloading the archived script does not invoke an LLM.

The focused export/parity suite passed before this marker was written. Final backend freeze requires Synthesis measurement hardening, Backend Release Proof, and Private Runtime contract to pass on this exact checkpoint SHA.

This marker does not authorize merge or deployment.
