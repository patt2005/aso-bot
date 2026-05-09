"""Export scored keywords + competitor list into a single .xlsx file.

The COMPETITORS sheet adds clickable hyperlinks on each App ID so the
recipient can open the upup analysis page directly from Excel.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from openpyxl.styles import Font

from core.models import Competitor, ScoredKeyword


UPUP_APP_URL = "https://www.upup.com/app/{app_id}/ios-aso?market=1&country={country}"
LINK_FONT = Font(color="0563C1", underline="single")


def to_excel(
    classified: dict[str, list[ScoredKeyword]],
    competitors: list[Competitor],
    output_path: str | Path,
    country: int = 25,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    name_by_id = {c.app_id: (c.name or c.app_id) for c in competitors}

    df_best = _scored_to_df(classified.get("BEST", []), name_by_id)
    df_medium = _scored_to_df(classified.get("MEDIUM", []), name_by_id)
    df_competitors = _competitors_to_df(competitors, country)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_best.to_excel(writer, sheet_name="BEST", index=False)
        df_medium.to_excel(writer, sheet_name="MEDIUM", index=False)
        df_competitors.to_excel(writer, sheet_name="COMPETITORS", index=False)

        _hyperlink_competitor_ids(writer.sheets["COMPETITORS"], competitors, country)

    return output_path


def _scored_to_df(items: list[ScoredKeyword], name_by_id: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Keyword": k.name,
            "Score": k.score,
            "Popularity": k.popularity,
            "Competitor count": k.competitor_count,
            "Avg competitor rank": k.avg_competitor_ranking,
            "Competitors": ", ".join(name_by_id.get(cid, cid) for cid in k.competitors),
        }
        for k in items
    ])


def _competitors_to_df(items: list[Competitor], country: int) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "App ID": c.app_id,
            "Name": c.name,
            "Category": c.category,
            "Seed overlap %": round(c.seed_overlap * 100, 1),
            "Matched seeds": ", ".join(c.matched_seeds),
            "Validated": "YES" if c.validated else "NO",
            "Keywords scraped": len(c.keywords),
            "Upup link": UPUP_APP_URL.format(app_id=c.app_id, country=country),
        }
        for c in items
    ])


def _hyperlink_competitor_ids(sheet, competitors: list[Competitor], country: int) -> None:
    headers = [cell.value for cell in sheet[1]]
    try:
        app_id_col = headers.index("App ID") + 1
        link_col = headers.index("Upup link") + 1
    except ValueError:
        return

    for row_idx, comp in enumerate(competitors, start=2):
        url = UPUP_APP_URL.format(app_id=comp.app_id, country=country)

        id_cell = sheet.cell(row=row_idx, column=app_id_col)
        id_cell.hyperlink = url
        id_cell.font = LINK_FONT

        link_cell = sheet.cell(row=row_idx, column=link_col)
        link_cell.hyperlink = url
        link_cell.font = LINK_FONT
