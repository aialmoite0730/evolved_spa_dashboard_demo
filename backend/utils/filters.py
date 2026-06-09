"""
SQL filter helpers.

All functions return (clause_string, params_list) tuples that can be
interpolated directly into f-string SQL.  Callers are responsible for
merging returned params into their master params list (deduplicating by name).
"""

from typing import Optional
from google.cloud import bigquery


def build_date_filter(
    start: Optional[str],
    end: Optional[str],
    locations: Optional[list[str]],
    date_col: str = "sale_date",
    loc_col:  str = "center_name",
) -> tuple[str, list]:
    """
    Build a WHERE clause for sales / appointment queries.

    Returns (where_clause, params).
    The returned params use the canonical names @start_date, @end_date, @locations.
    """
    conditions: list[str] = []
    params:     list      = []

    if start:
        conditions.append(f"DATE({date_col}) >= @start_date")
        params.append(bigquery.ScalarQueryParameter("start_date", "DATE", start))
    if end:
        conditions.append(f"DATE({date_col}) <= @end_date")
        params.append(bigquery.ScalarQueryParameter("end_date", "DATE", end))
    if locations:
        conditions.append(f"{loc_col} IN UNNEST(@locations)")
        params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


def build_sched_filter(
    s: Optional[str],
    e: Optional[str],
    locations: Optional[list[str]],
    sched_params_raw: list,
) -> tuple[str, list]:
    """
    Build a self-contained WHERE block for the employee_schedule table.

    • Date params are renamed sched_start / sched_end to avoid collision
      with the main query's @start_date / @end_date.
    • @locations is assumed to already be in the master params list — no
      duplicate ArrayQueryParameter is added here.
    • The role + hours guard ('Treatment Provider' | 'Esthetician',
      scheduled_hours > 0) is always appended so callers never need to
      add a second WHERE after this block.

    Returns (filter_block_string, extra_params_to_merge).
    """
    conds: list[str] = []
    extra: list      = []

    if s:
        conds.append("DATE(date) >= @sched_start")
    if e:
        conds.append("DATE(date) <= @sched_end")
    if locations:
        conds.append("center_name IN UNNEST(@locations)")   # reuse existing param

    # Always filter to billable clinical roles only
    conds.append("job_name IN ('Treatment Provider', 'Esthetician')")
    conds.append("scheduled_hours > 0")

    filter_block = "WHERE " + " AND ".join(conds)

    # Rename date params so they don't collide with main @start_date / @end_date
    for p in sched_params_raw:
        if p.name == "start_date":
            extra.append(bigquery.ScalarQueryParameter("sched_start", "DATE", p.value))
        elif p.name == "end_date":
            extra.append(bigquery.ScalarQueryParameter("sched_end",   "DATE", p.value))
        # "locations" intentionally skipped — already in master params

    return filter_block, extra


def build_join_where(where: str) -> str:
    """
    Scope a sales WHERE clause to the 'sa' alias used in JOIN queries.

    Rewrites:
      DATE(sale_date)  →  DATE(sa.sale_date)
      center_name      →  sa.center_name
    """
    if not where:
        return ""
    return (
        where
        .replace("DATE(sale_date)", "DATE(sa.sale_date)")
        .replace("center_name",    "sa.center_name")
    )


def merge_params(base: list, *extra_lists: list) -> list:
    """
    Merge multiple param lists, skipping duplicates by parameter name.
    First occurrence wins — preserves order deterministically.
    """
    seen:   set  = {p.name for p in base}
    result: list = list(base)
    for params in extra_lists:
        for p in params:
            if p.name not in seen:
                result.append(p)
                seen.add(p.name)
    return result
