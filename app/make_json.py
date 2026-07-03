import json
import re
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"
DOCS_DIR = BASE_DIR / "docs"
OUTPUT_FILE = DOCS_DIR / "data.json"

PARTS = {
    "part1": {
        "label": "1部",
        "slots": ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00"],
        "start_min": "09:00",
        "start_max": "14:59",
    },
    "part2": {
    "label": "2部",
    "slots": [
        "15:00", "15:30", "16:00", "16:30", "17:00",
        "17:30", "18:00", "18:30", "19:00"
    ],
    "start_min": "15:00",
    "start_max": "23:59",
},
}


def clean_job_name(name):
    if pd.isna(name):
        return ""
    name = str(name)
    name = re.sub(r"\[([^=\]]+)=([^\]]+)\]", r"\1", name)
    return name.strip()


def load_raw_csv():
    files = sorted(RAW_DIR.glob("kandu_*.csv"))
    if not files:
        print("CSVがありません")
        return pd.DataFrame()

    frames = []
    for file in files:
        try:
            frames.append(pd.read_csv(file))
        except Exception as e:
            print(f"読み込み失敗: {file} / {e}")

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def floor_to_30min(dt):
    minute = 0 if dt.minute < 30 else 30
    return f"{dt.hour:02d}:{minute:02d}"


def detect_part_by_slot(slot):
    for part_key, config in PARTS.items():
        if slot in config["slots"]:
            return part_key
    return None


def detect_part_by_start(start):
    if pd.isna(start):
        return None

    start = str(start)

    for part_key, config in PARTS.items():
        if config["start_min"] <= start <= config["start_max"]:
            return part_key

    return None


def normalize_df(df):
    df = df.copy()

    required = ["取得時刻", "職業", "定員", "開始", "体験時間", "残席"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"CSVに必要な列がありません: {missing}")

    df["職業"] = df["職業"].apply(clean_job_name)
    df["取得時刻"] = pd.to_datetime(df["取得時刻"], errors="coerce")
    df = df[df["取得時刻"].notna()]

    df["取得日"] = df["取得時刻"].dt.strftime("%Y-%m-%d")
    df["取得枠"] = df["取得時刻"].apply(floor_to_30min)

    df["取得部"] = df["取得枠"].apply(detect_part_by_slot)
    df["開始部"] = df["開始"].apply(detect_part_by_start)

    df = df[df["取得部"].notna()]
    df = df[df["開始部"].notna()]
    df = df[df["取得部"] == df["開始部"]]

    for col in ["定員", "体験時間", "残席"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    return df


def latest_snapshot(part_df):
    latest_slot = part_df["取得枠"].max()
    return part_df[part_df["取得枠"] == latest_slot].copy()


def make_ranking(part_df):
    latest_df = latest_snapshot(part_df)

    summary = (
        latest_df.groupby("職業", as_index=False)
        .agg(
            capacity_total=("定員", "sum"),
            remaining_total=("残席", "sum"),
            sessions=("開始", "count"),
        )
    )

    summary["reserved_total"] = summary["capacity_total"] - summary["remaining_total"]
    summary["reserved_rate"] = summary.apply(
        lambda row: row["reserved_total"] / row["capacity_total"] if row["capacity_total"] > 0 else 0,
        axis=1
    )

    summary = summary.sort_values(
        ["reserved_rate", "remaining_total", "sessions", "職業"],
        ascending=[False, True, True, True]
    ).head(10)

    ranking = []
    for _, row in summary.iterrows():
        ranking.append({
            "rank": len(ranking) + 1,
            "name": row["職業"],
            "reserved_rate": round(float(row["reserved_rate"]) * 100, 1),
            "reserved_total": int(row["reserved_total"]),
            "capacity_total": int(row["capacity_total"]),
            "remaining_total": int(row["remaining_total"]),
            "sessions": int(row["sessions"]),
        })

    return ranking


def make_summary(part_df):
    latest_df = latest_snapshot(part_df)

    summary = (
        latest_df.groupby("職業", as_index=False)
        .agg(
            capacity_total=("定員", "sum"),
            remaining_total=("残席", "sum"),
            sessions=("開始", "count"),
            capacity=("定員", "max"),
            duration=("体験時間", "max"),
        )
    )

    summary["reserved_total"] = summary["capacity_total"] - summary["remaining_total"]
    summary["reserved_rate"] = summary.apply(
        lambda row: row["reserved_total"] / row["capacity_total"] if row["capacity_total"] > 0 else 0,
        axis=1
    )

    summary = summary.sort_values(
        ["reserved_rate", "remaining_total", "職業"],
        ascending=[False, True, True]
    )

    return [
        {
            "name": row["職業"],
            "capacity": int(row["capacity"]),
            "duration": int(row["duration"]),
            "sessions": int(row["sessions"]),
            "capacity_total": int(row["capacity_total"]),
            "reserved_total": int(row["reserved_total"]),
            "remaining_total": int(row["remaining_total"]),
            "reserved_rate": round(float(row["reserved_rate"]) * 100, 1),
        }
        for _, row in summary.iterrows()
    ]


def make_pivot(part_df, slots):
    pivot_df = (
        part_df.pivot_table(
            index=["職業", "開始"],
            columns="取得枠",
            values="残席",
            aggfunc="min",
        )
        .reset_index()
        .sort_values(["職業", "開始"])
    )

    rows = []

    for _, row in pivot_df.iterrows():
        values = {}

        for slot in slots:
            if slot in pivot_df.columns:
                value = row[slot]
                values[slot] = "" if pd.isna(value) else int(value)
            else:
                values[slot] = ""

        rows.append({
            "job": row["職業"],
            "start": row["開始"],
            "values": values,
        })

    return {
        "times": slots,
        "rows": rows,
    }


def make_part(part_df, part_key):
    config = PARTS[part_key]
    latest_time = part_df["取得時刻"].max()

    return {
        "label": config["label"],
        "updated_at": latest_time.strftime("%Y/%m/%d %H:%M"),
        "times": config["slots"],
        "ranking": make_ranking(part_df),
        "summary": make_summary(part_df),
        "pivot": make_pivot(part_df, config["slots"]),
    }


def build_json(df):
    result = {"dates": {}}

    for date, day_df in df.groupby("取得日"):
        parts = {}

        for part_key in PARTS:
            part_df = day_df[day_df["取得部"] == part_key].copy()
            if not part_df.empty:
                parts[part_key] = make_part(part_df, part_key)

        if parts:
            latest_time = day_df["取得時刻"].max()
            result["dates"][date] = {
                "updated_at": latest_time.strftime("%Y/%m/%d %H:%M"),
                "parts": parts,
            }

    return result


def main():
    df = load_raw_csv()

    if df.empty:
        print("処理するCSVがありません")
        return

    df = normalize_df(df)

    if df.empty:
        print("有効なデータがありません")
        return

    result = build_json(df)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"{OUTPUT_FILE} を更新しました")
    print(f"{len(result['dates'])}日分のデータを書き出しました")


if __name__ == "__main__":
    main()