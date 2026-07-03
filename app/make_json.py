import json
import re
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"
DOCS_DIR = BASE_DIR / "docs"
OUTPUT_FILE = DOCS_DIR / "data.json"


def clean_job_name(name):
    if pd.isna(name):
        return ""

    name = str(name)
    name = re.sub(r"\[([^=\]]+)=([^\]]+)\]", r"\1", name)
    name = name.strip()
    return name


def load_all_csv():
    files = sorted(RAW_DIR.glob("kandu_*.csv"))

    if not files:
        print("CSVがありません")
        return pd.DataFrame()

    df = pd.concat(
        [pd.read_csv(file) for file in files],
        ignore_index=True
    )

    return df


def make_ranking(day_df):
    latest_time = day_df["取得時刻"].max()
    latest_df = day_df[day_df["取得時刻"] == latest_time].copy()

    summary = (
        latest_df.groupby("職業")
        .agg(
            残席合計=("残席", "sum"),
            開催回数=("開始", "count"),
            定員=("定員", "max"),
            体験時間=("体験時間", "max"),
        )
        .reset_index()
    )

    summary = summary.sort_values(["残席合計", "開催回数"], ascending=[True, True])

    ranking = []

    for idx, row in summary.head(10).iterrows():
        ranking.append({
            "rank": len(ranking) + 1,
            "name": row["職業"],
            "remaining_total": int(row["残席合計"]),
            "sessions": int(row["開催回数"]),
        })

    return ranking


def make_summary(day_df):
    latest_time = day_df["取得時刻"].max()
    latest_df = day_df[day_df["取得時刻"] == latest_time].copy()

    summary = (
        latest_df.groupby("職業")
        .agg(
            定員=("定員", "max"),
            体験時間=("体験時間", "max"),
            開催回数=("開始", "count"),
            残席合計=("残席", "sum"),
        )
        .reset_index()
        .sort_values(["残席合計", "職業"], ascending=[True, True])
    )

    return [
        {
            "name": row["職業"],
            "capacity": int(row["定員"]) if pd.notna(row["定員"]) else "",
            "duration": int(row["体験時間"]) if pd.notna(row["体験時間"]) else "",
            "sessions": int(row["開催回数"]),
            "remaining_total": int(row["残席合計"]),
        }
        for _, row in summary.iterrows()
    ]


def make_pivot(day_df):
    pivot = pd.pivot_table(
        day_df,
        index=["職業", "開始"],
        columns="取得時刻表示",
        values="残席",
        aggfunc="min"
    )

    pivot = pivot.sort_index(level=[0, 1])
    pivot = pivot.reset_index()

    time_columns = [
        col for col in pivot.columns
        if col not in ["職業", "開始"]
    ]

    rows = []

    for _, row in pivot.iterrows():
        values = {}

        for col in time_columns:
            value = row[col]
            values[col] = "" if pd.isna(value) else int(value)

        rows.append({
            "job": row["職業"],
            "start": row["開始"],
            "values": values
        })

    return {
        "times": time_columns,
        "rows": rows
    }


def main():
    df = load_all_csv()

    if df.empty:
        return

    df["職業"] = df["職業"].apply(clean_job_name)

    df["取得時刻"] = pd.to_datetime(df["取得時刻"])
    df["取得日"] = df["取得時刻"].dt.strftime("%Y-%m-%d")
    df["取得時刻表示"] = df["取得時刻"].dt.strftime("%H:%M")

    df["残席"] = pd.to_numeric(df["残席"], errors="coerce").fillna(0).astype(int)

    result = {
        "dates": {}
    }

    for date, day_df in df.groupby("取得日"):
        latest_time = day_df["取得時刻"].max()

        result["dates"][date] = {
            "updated_at": latest_time.strftime("%Y/%m/%d %H:%M"),
            "ranking": make_ranking(day_df),
            "summary": make_summary(day_df),
            "pivot": make_pivot(day_df)
        }

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"{OUTPUT_FILE} を更新しました")
    print(f"{len(result['dates'])}日分のデータを書き出しました")


if __name__ == "__main__":
    main()
