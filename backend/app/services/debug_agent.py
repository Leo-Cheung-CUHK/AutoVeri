"""
DebugAgent: Uses GPT-4o to analyse simulation errors and generate a fix.
"""

import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an expert RTL/UVM verification engineer with deep knowledge of:
- SystemVerilog and UVM methodology
- RTL design patterns and common bugs
- Testbench architecture and driver/monitor/scoreboard patterns
- Timing, reset, and interface protocol issues

Your task is to analyse simulation errors, understand the root cause from the git diff and
code context provided, and propose a minimal, correct fix.

Respond ONLY with a valid JSON object matching this schema (no markdown, no extra text):
{
  "root_cause": "<concise description of the root cause>",
  "fix_target": "<TB_ERROR | RTL_ERROR | null>",
  "confidence": "<high | medium | low>",
  "explanation": "<detailed explanation of why this error occurs and how the fix resolves it>",
  "patch": "<unified diff patch string, or null if no automated fix is safe to apply>"
}

Guidelines:
- If multiple errors share a single root cause, describe the root cause once.
- Set fix_target to null if the fix requires human judgment.
- Set confidence to 'low' if the context is insufficient to be certain.
- The patch must be a valid unified diff (--- a/file / +++ b/file format).
- If you cannot generate a safe patch, set patch to null and explain why in explanation.
- Never hallucinate file paths or line numbers not present in the provided context.
"""


def _build_user_prompt(
    errors: list[dict],
    git_diff: str,
    error_contexts: list[dict],
) -> str:
    """Build the structured user prompt."""
    errors_block = json.dumps(errors, indent=2)

    contexts_block = ""
    for ctx in error_contexts:
        file_path = ctx.get("file", "unknown")
        line = ctx.get("line", "?")
        content = ctx.get("content", "")
        contexts_block += f"\n### {file_path} (around line {line})\n```\n{content}\n```\n"

    diff_block = git_diff if git_diff else "(no diff available)"

    return f"""\
## Simulation Errors

```json
{errors_block}
```

## Git Diff (changes that triggered this simulation run)

```diff
{diff_block}
```

## Code Context (source lines around each error)

{contexts_block if contexts_block else "(no source context available)"}

---
Analyse the errors above, considering the git diff that introduced them and the code context.
Identify the root cause and provide a fix as described in your instructions.
"""


class DebugAgent:
    """
    Calls GPT-4o to produce a structured DebugResult from simulation errors.

    Usage:
        agent = DebugAgent()
        result = await agent.analyse(errors, git_diff, error_contexts)
    """

    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    async def analyse(
        self,
        errors: list[dict],
        git_diff: str,
        error_contexts: list[dict] | None = None,
    ) -> dict:
        """
        Analyse errors and return a DebugResult dict.

        Args:
            errors: List of ParsedError dicts.
            git_diff: The unified diff of changes that triggered the job.
            error_contexts: Optional list of {file, line, content} dicts with
                            source code around each error location.

        Returns:
            dict with keys: root_cause, fix_target, confidence, explanation, patch
        """
        if not errors:
            return self._fallback("No errors were provided for analysis.")

        contexts = error_contexts or []
        user_prompt = _build_user_prompt(errors, git_diff, contexts)

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )

            raw = response.choices[0].message.content
            if not raw:
                return self._fallback("GPT-4o returned an empty response.")

            result = json.loads(raw)
            return self._validate_and_normalise(result)

        except json.JSONDecodeError as exc:
            logger.error("Failed to parse GPT-4o JSON response: %s", exc)
            return self._fallback(f"Could not parse AI response as JSON: {exc}")
        except Exception as exc:
            logger.exception("DebugAgent.analyse failed: %s", exc)
            return self._fallback(f"AI analysis failed: {exc}")

    @staticmethod
    def _validate_and_normalise(raw: dict) -> dict:
        """Ensure all required keys are present and values are within allowed enums."""
        allowed_fix_targets = {"TB_ERROR", "RTL_ERROR", None}
        allowed_confidence = {"high", "medium", "low"}

        fix_target = raw.get("fix_target")
        if fix_target not in allowed_fix_targets:
            fix_target = None

        confidence = raw.get("confidence", "low")
        if confidence not in allowed_confidence:
            confidence = "low"

        return {
            "root_cause": str(raw.get("root_cause", "Unknown root cause")),
            "fix_target": fix_target,
            "confidence": confidence,
            "explanation": str(raw.get("explanation", "")),
            "patch": raw.get("patch") or None,
        }

    @staticmethod
    def _fallback(reason: str) -> dict:
        """Return a safe fallback DebugResult when analysis cannot be completed."""
        return {
            "root_cause": "Analysis could not be completed.",
            "fix_target": None,
            "confidence": "low",
            "explanation": reason,
            "patch": None,
        }
