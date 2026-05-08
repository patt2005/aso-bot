"""Export scored keywords + competitor list into a single .xlsx file."""
from __future__ import annotations
from pathlib import Path
import pandas as pd

from core.models import Competitor, ScoredKeyword


def to_excel(
    classified: dict[str, list[ScoredKeyword]],
    competitors: list[Competitor],
    output_path: str | Path,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df_best = _scored_to_df(classified.get("BEST", []))
    df_medium = _scored_to_df(classified.get("MEDIUM", []))
    df_competitors = _competitors_to_df(competitors)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_best.to_excel(writer, sheet_name="BEST", index=False)
        df_medium.to_excel(writer, sheet_name="MEDIUM", index=False)
        df_competitors.to_excel(writer, sheet_name="COMPETITORS", index=False)

    return output_path


def _scored_to_df(items: list[ScoredKeyword]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Keyword": k.name,
            "Score": k.score,
            "Popularity": k.popularity,
            "Competitor count": k.competitor_count,
            "Avg competitor rank": k.avg_competitor_ranking,
            "Competitors": ", ".join(k.competitors),
        }
        for k in items
    ])


def _competitors_to_df(items: list[Competitor]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "App ID": c.app_id,
            "Name": c.name,
            "Category": c.category,
            "Seed overlap %": round(c.seed_overlap * 100, 1),
            "Matched seeds": ", ".join(c.matched_seeds),
            "Validated": "YES" if c.validated else "NO",
            "Keywords scraped": len(c.keywords),
        }
        for c in items
    ])
