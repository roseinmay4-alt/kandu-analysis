import json
import re
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"
DOCS_DIR = BASE_DIR / "docs"
OUTPUT_FILE = DOCS_DIR / "data.json"

PART1_TIMES = [
    "09:00", "09:30", "10:00", "10:30", "11:00",
    "11:30", "12:00", "12:30", "13:00"
]

PART2_TIMES = [
    "15:00", "15:30", "16:00", "16:30",
    "17:00", "17:30", "18:00", "18:30"
]


def clean_job_name(name):
    if pd.isna(name):
        return ""

    name = str(name)
    name = re.sub(r"\[([^=\]]+)=([^\]]+)\]", r"\1", name)
    return name.strip()


def load_all_csv():
    files = sorted(RAW_DIR.glob("kandu_*.csv"))

    if not files:
        print("CSVがありません")
        return pd.DataFrame()

    return pd.concat([pd.read_csv(file) for file in files], ignore_index=True)


def round_to_slot(dt):
    hour = dt.hour
    minute = dt.minute

    if minute < 30:
        return f"{hour:02d}:00"
    return f"{hour:02d}:30"


def get_part_by_slot(slot):
    if slot in PART1_TIMES:
        return "part1"
    if slot in PART2_TIMES:
        return "part2"
    return None


def get_part_by_start_time(start):
    if not isinstance(start, str) or ":" not in start:
        return None

    hour = int(start.split(":")[0])

    if 9 <= hour < 15:
        return "part1"

    if hour >= 15:
        return "part2"

    return None


def make_ranking(part_df):
    latest_slot = part_df["取得枠"].max()
    latest_df = part_df[part_df["取得枠"] == latest_slot].copy()

    summary = (
        latest_df.groupby("職業")
        .agg(
            残席合計=("残席", "sum"),
            開催回数=("開始", "count"),
            定員=("定員", "max"),
            体験時間=("体験時間", "max"),
        )
        .reset_index()
        .sort_values(["残席合計", "開催回数"], ascending=[True, True])
    )

    ranking = []

    for _, row in summary.head(10).iterrows():
        ranking.append({
            "rank": len(ranking) + 1,
            "name": row["職業"],
            "remaining_total": int(row["残席合計"]),
            "sessions": int(row["開催回数"]),
        })

    return ranking


def make_summary(part_df):
    latest_slot = part_df["取得枠"].max()
    latest_df = part_df[part_df["取得枠"] == latest_slot].copy()

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


def make_pivot(part_df, fixed_times):
    pivot = pd.pivot_table(
        part_df,
        index=["職業", "開始"],
        columns="取得枠",
        values="残席",
        aggfunc="min"
    )

    pivot = pivot.reset_index()
    pivot = pivot.sort_values(["職業", "開始"])

    rows = []

    for _, row in pivot.iterrows():
        values = {}

        for time in fixed_times:
            value = row[time] if time in row.index else ""
           

        rows.append({
            "job": row["職業"],
            "start": row["開始"],
            "values": values
        })

    return {
        "times": fixed_times,
        "rows": rows
    }


def make_part_data(part_df, label, fixed_times):
    latest_time = part_df["取得時刻"].max()

    return {
        "label": label,
        "updated_at": latest_time.strftime("%Y/%m/%d %H:%M"),
        "times": fixed_times,
        "ranking": make_ranking(part_df),
        "summary": make_summary(part_df),
        "pivot": make_pivot(part_df, fixed_times)
    }


def main():
    df = load_all_csv()

    if df.empty:
        return

    df["職業"] = df["職業"].apply(clean_job_name)
    df["取得時刻"] = pd.to_datetime(df["取得時刻"])
    df["取得日"] = df["取得時刻"].dt.strftime("%Y-%m-%d")
    df["取得枠"] = df["取得時刻"].apply(round_to_slot)

    df["残席"] = pd.to_numeric(df["残席"], errors="coerce").fillna(0).astype(int)
    df["定員"] = pd.to_numeric(df["定員"], errors="coerce").fillna(0).astype(int)
    df["体験時間"] = pd.to_numeric(df["体験時間"], errors="coerce").fillna(0).astype(int)

    df["部"] = df["取得枠"].apply(get_part_by_slot)
    df["開始部"] = df["開始"].apply(get_part_by_start_time)

    df = df[df["部"].notna()]
    df = df[df["部"] == df["開始部"]]

    result = {
        "dates": {}
    }

    for date, day_df in df.groupby("取得日"):
        parts = {}

        part1_df = day_df[day_df["部"] == "part1"].copy()
        if not part1_df.empty:
            parts["part1"] = make_part_data(part1_df, "1部", PART1_TIMES)

        part2_df = day_df[day_df["部"] == "part2"].copy()
        if not part2_df.empty:
            parts["part2"] = make_part_data(part2_df, "2部", PART2_TIMES)

        if parts:
            latest_time = day_df["取得時刻"].max()

            result["dates"][date] = {
                "updated_at": latest_time.strftime("%Y/%m/%d %H:%M"),
                "parts": parts
            }

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"{OUTPUT_FILE} を更新しました")
    print(f"{len(result['dates'])}日分のデータを書き出しました")


if __name__ == "__main__":
    main()