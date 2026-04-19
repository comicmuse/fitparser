from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import yaml
from openai import OpenAI

from runcoach.config import Config
from runcoach.db import RunCoachDB

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a world-class running trainer like Greg Palladino.

{athlete_profile}

Be encouraging but realistic. Remind me about prehab and strength and conditioning \
periodically.

Any assertions should be based on the information in the YAML data provided. Do not \
infer data that is not there without clearly highlighting it.

Use metrics from the data in your summary. Do not guess metrics.

If you can, recommend actionable takeaways for my training, but only if there's \
something real to address or work on.

You will receive two YAML documents separated by a "---" delimiter:

1. **Training context** – a summary of the previous 7 days of training, including \
running stress scores (RSS), training load (ATL/CTL/RSB), and a per-activity breakdown. \
Use this to contextualise your analysis: is the athlete fatigued or fresh? Is this \
session consistent with recent training load? Are there any patterns to flag?

2. **Current workout** – the detailed data for the session being analysed.

RSS (Running Stress Score) is analogous to Stryd's RSS model: \
RSS = (duration_h) * (avg_power / CP)^2 * 100. \
ATL is the 7-day average daily RSS (acute load). \
CTL is the 42-day average daily RSS (chronic load). \
RSB = CTL - ATL (Running Stress Balance: positive = fresh, negative = fatigued).

The training context may contain a **prescribed_workout** field showing \
what the Stryd training plan prescribed for the day being analysed. \
When present, compare the actual execution against the prescription: \
did the athlete hit the target power zones, duration, and distance? \
Were they under or over the planned stress? Call out meaningful deviations \
(positive or negative) but avoid nitpicking minor differences.

The training context may also contain **next_scheduled_workouts** listing \
the next 1-2 upcoming sessions from the training plan. Use this to give \
brief forward-looking advice: how should the athlete prepare or recover \
for what's coming next? Keep this to 1-2 sentences at most.

Below is the JSON Schema that describes the workout YAML data format:

```json
{schema}
```
"""

RACE_CONTEXT_PROMPT = """\

Current race goal: {race_distance} on {race_date}
Days until race: {days_until_race}
Training phase: {training_phase}
Current date: {current_date}

Consider the athlete's position in their training cycle when analyzing this workout. \
Provide guidance appropriate to their current training phase ({training_phase}) and \
proximity to race day.
"""

RACE_DISTANCES = [
    "5K",
    "10K",
    "15K",
    "10 Mile",
    "Half Marathon",
    "Marathon",
]


def _training_phase(days_until_race: int) -> str:
    """Return a training phase label based on days until race."""
    weeks = days_until_race / 7
    if days_until_race < 0:
        if days_until_race >= -28:
            return "Recovery"
        return "Post-race"
    if weeks <= 1:
        return "Race Week"
    if weeks <= 2:
        return "Taper"
    if weeks <= 8:
        return "Peak Training"
    if weeks <= 16:
        return "Build Phase"
    return "Base Building"


def _load_athlete_profile(db: RunCoachDB | None = None, user_id: int | None = None) -> str:
    """Load the athlete profile from the database for the given user."""
    if db is not None and user_id is not None:
        return db.get_athlete_profile(user_id)
    return ""


def _load_race_goal(db: RunCoachDB | None = None, user_id: int | None = None) -> dict:
    """Load the race goal (race_date, race_distance) from the database."""
    if db is not None and user_id is not None:
        return db.get_race_goal(user_id)
    return {"race_date": None, "race_distance": None}


def _load_schema(project_root: Path | None = None) -> str:
    """Load the workout YAML schema JSON."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent
    schema_path = project_root / "workout_yaml_schema.json"
    if schema_path.exists():
        return schema_path.read_text(encoding="utf-8")
    return "{}"


def _call_openai(system_msg: str, user_msg: str, config: Config) -> dict:
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


def _call_claude(system_msg: str, user_msg: str, config: Config) -> dict:
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError(
            "The 'anthropic' package is required for Claude support. "
            "Install it with: pip install anthropic"
        ) from exc
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    response = client.messages.create(
        model=config.anthropic_model,
        max_tokens=8192,
        system=system_msg,
        messages=[{"role": "user", "content": user_msg}],
    )
    return {
        "commentary": response.content[0].text,
        "prompt_tokens": response.usage.input_tokens if response.usage else None,
        "completion_tokens": response.usage.output_tokens if response.usage else None,
    }


def _call_ollama(system_msg: str, user_msg: str, config: Config) -> dict:
    base_url = config.ollama_base_url.rstrip("/") + "/v1"
    client = OpenAI(base_url=base_url, api_key="ollama")
    response = client.chat.completions.create(
        model=config.ollama_model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        extra_body={"options": {"num_ctx": config.ollama_num_ctx}},
    )
    choice = response.choices[0]
    usage = response.usage
    return {
        "commentary": choice.message.content,
        "prompt_tokens": usage.prompt_tokens if usage else None,
        "completion_tokens": usage.completion_tokens if usage else None,
    }


def _dispatch_llm(system_msg: str, user_msg: str, config: Config) -> dict:
    provider = config.llm_provider
    log.info("Using LLM provider: %s", provider)
    if provider == "claude":
        return _call_claude(system_msg, user_msg, config)
    if provider == "ollama":
        return _call_ollama(system_msg, user_msg, config)
    return _call_openai(system_msg, user_msg, config)


def analyze_run(
    yaml_content: str,
    config: Config,
    context_yaml: str | None = None,
    db: RunCoachDB | None = None,
    run_date: str | None = None,
    user_id: int | None = None,
) -> dict:
    """
    Send YAML workout data to the LLM for coaching analysis.

    If context_yaml is provided, it is prepended as a separate YAML document.

    Returns a dict with keys: commentary, prompt_tokens, completion_tokens.
    """
    schema = _load_schema()
    profile = _load_athlete_profile(db, user_id)
    system_msg = SYSTEM_PROMPT.format(schema=schema, athlete_profile=profile)

    # Append race context if a race goal is set
    race_goal = _load_race_goal(db, user_id)
    race_date_str = race_goal.get("race_date")
    race_distance = race_goal.get("race_distance")
    if race_date_str and race_distance:
        try:
            race_date = date.fromisoformat(race_date_str)
            current = date.fromisoformat(run_date) if run_date else date.today()
            days_until = (race_date - current).days
            phase = _training_phase(days_until)
            system_msg += RACE_CONTEXT_PROMPT.format(
                race_distance=race_distance,
                race_date=race_date_str,
                days_until_race=days_until,
                training_phase=phase,
                current_date=current.isoformat(),
            )
        except (ValueError, TypeError):
            pass  # Malformed race_date — skip the race context block

    # Check if this is a manual upload and add a note to the prompt
    if "manual_upload: true" in yaml_content:
        system_msg += (
            "\n\nNOTE: This run was manually uploaded and may not have Stryd power data. "
            "Do not penalise or comment on missing power data for manual uploads. "
            "Focus on HR, pace, and other available metrics instead."
        )

    if context_yaml:
        user_msg = context_yaml.rstrip("\n") + "\n---\n" + yaml_content
    else:
        user_msg = yaml_content

    return _dispatch_llm(system_msg, user_msg, config)


def analyze_and_write(
    yaml_path: Path,
    config: Config,
    db: RunCoachDB | None = None,
    user_id: int | None = None,
) -> tuple[Path, dict]:
    """
    Read a YAML file, build training context, analyze it, write the .md file.

    Returns (md_path, result_dict).
    """
    yaml_content = yaml_path.read_text(encoding="utf-8")

    # Build weekly training context if we have a DB reference
    context_yaml = None
    run_date: str | None = None
    if db is not None:
        try:
            parsed = yaml.safe_load(yaml_content)
            run_date = parsed.get("date")
            current_cp = parsed.get("critical_power")
            if run_date:
                from runcoach.context import build_weekly_context
                context = build_weekly_context(
                    run_date,
                    config.data_dir,
                    db,
                    current_cp=current_cp,
                    user_id=user_id,
                )
                context_yaml = yaml.safe_dump(context, sort_keys=False, allow_unicode=True)
        except Exception:
            log.exception("Failed to build training context, proceeding without it")

    result = analyze_run(
        yaml_content, config, context_yaml=context_yaml, db=db,
        run_date=run_date, user_id=user_id,
    )

    md_path = yaml_path.with_suffix(".md")
    md_path.write_text(result["commentary"], encoding="utf-8")
    log.info("Wrote %s", md_path)

    return md_path, result
