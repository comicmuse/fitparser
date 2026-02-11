from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml
from openai import OpenAI

from runcoach.config import Config
from runcoach.db import RunCoachDB

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
I'm running the London Marathon on 26 April 2026. You are a world-class running \
trainer like Greg Palladino.

I'm training using a Stryd training plan, targetting power.

Be encouraging but realistic. Remind me about prehab and strength and conditioning \
periodically.

Whenever interpreting Stryd data, my weight is configured to 61Kg on my Stryd pod, \
so if you're doing any maths, bear that in mind. There's no need to tell me about this\
this or explain it to me, just use it in your calculations.

Any assertions should be based on the information in the YAML data provided. Do not \
infer data that is not there without clearly highlighting it.

Use metrics from the data in your summary. Do not guess metrics.

If you can, recommend actionable takeaways for my training, but only if there's \
something real to address or work on.

You will receive two YAML documents separated by a "---" delimiter:

1. **Training context** – a summary of the previous 7 days of training, including \
running stress scores (RSS), training load (ATL/CTL/TSB), and a per-activity breakdown. \
Use this to contextualise your analysis: is the athlete fatigued or fresh? Is this \
session consistent with recent training load? Are there any patterns to flag?

2. **Current workout** – the detailed data for the session being analysed.

RSS (Running Stress Score) is analogous to Stryd's RSS model: \
RSS = (duration_h) * (avg_power / CP)^2 * 100. \
ATL is the 7-day average daily RSS (acute load). \
CTL is the 28-day average daily RSS (chronic load). \
TSB = CTL - ATL (positive = fresh, negative = fatigued).

Below is the JSON Schema that describes the workout YAML data format:

```json
{schema}
```
"""


def _load_schema(project_root: Path | None = None) -> str:
    """Load the workout YAML schema JSON."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent
    schema_path = project_root / "workout_yaml_schema.json"
    if schema_path.exists():
        return schema_path.read_text(encoding="utf-8")
    return "{}"


def analyze_run(
    yaml_content: str,
    config: Config,
    context_yaml: str | None = None,
) -> dict:
    """
    Send YAML workout data to the LLM for coaching analysis.

    If context_yaml is provided, it is prepended as a separate YAML document.

    Returns a dict with keys: commentary, prompt_tokens, completion_tokens.
    """
    schema = _load_schema()
    system_msg = SYSTEM_PROMPT.format(schema=schema)

    if context_yaml:
        user_msg = context_yaml.rstrip("\n") + "\n---\n" + yaml_content
    else:
        user_msg = yaml_content

    client = OpenAI(api_key=config.openai_api_key)
    response = client.chat.completions.create(
        model=config.openai_model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
    )

    choice = response.choices[0]
    usage = response.usage

    return {
        "commentary": choice.message.content,
        "prompt_tokens": usage.prompt_tokens if usage else None,
        "completion_tokens": usage.completion_tokens if usage else None,
    }


def analyze_and_write(
    yaml_path: Path,
    config: Config,
    db: RunCoachDB | None = None,
) -> tuple[Path, dict]:
    """
    Read a YAML file, build training context, analyze it, write the .md file.

    Returns (md_path, result_dict).
    """
    yaml_content = yaml_path.read_text(encoding="utf-8")

    # Build weekly training context if we have a DB reference
    context_yaml = None
    if db is not None:
        try:
            parsed = yaml.safe_load(yaml_content)
            run_date = parsed.get("date")
            if run_date:
                from runcoach.context import build_weekly_context
                context = build_weekly_context(run_date, config.data_dir, db)
                context_yaml = yaml.safe_dump(context, sort_keys=False, allow_unicode=True)
        except Exception:
            log.exception("Failed to build training context, proceeding without it")

    result = analyze_run(yaml_content, config, context_yaml=context_yaml)

    md_path = yaml_path.with_suffix(".md")
    md_path.write_text(result["commentary"], encoding="utf-8")
    log.info("Wrote %s", md_path)

    return md_path, result
