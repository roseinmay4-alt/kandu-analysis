import os
import glob
import json
import re
import pandas as pd


RAW_DIR = "data/raw"
OUTPUT_JSON = "docs/data.json"


def clean_job_name(name):
    name = str(name)
    name = re.sub(r"\[([^=\]]+)=([^\]]+)\]", r"\1", name)
    name = name.replace("[", "").replace("]", "")
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def normalize_columns(df):
    df = df.copy()

    rename_map = {
        "activity_name": "職業",
        "activity_name_ruby": "職業",
        "start": "開始",
        "start_time": "開始",
        "end": "終了",
        "end_time": "終了",
        "capacity": "定員",
        "possible_number": "定員",
        "remaining": "残席",
        "reservation_possibles": "残席",
        "fetched_at": "取得時刻",
        "取得時間": "取得時刻",
    }

    df = df.rename(columns={c: rename_map.get(c, c) for c in df.columns})
    return df


def load_all_csv():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "*.csv")))

    if not files:
        raise FileNotFoundError("data/raw にCSVがありません。")

    dfs = []

    for file in files:
        try:
            df = pd.read_csv(file, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(file, encoding="cp932")

        df = normalize_columns(df)
        df["source_file"] = os.path.basename(file)
        dfs.append(df)

    return pd.concat(dfs, ignore_index=True)


def clean_df(df):
    df = df.copy()

    required = ["職業", "開始", "終了", "定員", "残席", "取得時刻"]
    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(f"必要な列がありません: {missing}")

    df["職業"] = df["職業"].apply(clean_job_name)
    df["開始"] = df["開始"].astype(str).str.strip()
    df["終了"] = df["終了"].astype(str).str.strip()

    df["定員"] = pd.to_numeric(df["定員"], errors="coerce")
    df["残席"] = pd.to_numeric(df["残席"], errors="coerce")
    df["取得時刻_dt"] = pd.to_datetime(df["取得時刻"], errors="coerce")

    df = df.dropna(subset=["職業", "開始", "終了", "定員", "残席", "取得時刻_dt"])
    df = df[df["定員"] > 0]

    df["日付"] = df["取得時刻_dt"].dt.strftime("%Y-%m-%d")
    df["取得時刻表示"] = df["取得時刻_dt"].dt.strftime("%H:%M")

    return df


def time_to_minutes(t):
    try:
        h, m = str(t).split(":")[:2]
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def part_key_from_start(start):
    minutes = time_to_minutes(start)
    return "part2" if minutes >= 15 * 60 else "part1"


def make_part_data(day_df, part_key):
    part_df = day_df.copy()
    part_df["part_key"] = part_df["開始"].apply(part_key_from_start)
    part_df = part_df[part_df["part_key"] == part_key]

    if part_key == "part1":
        part_df = part_df[part_df["取得時刻_dt"].dt.hour < 15]
        label = "1部"
    else:
        part_df = part_df[part_df["取得時刻_dt"].dt.hour >= 15]
        label = "2部"

    if part_df.empty:
        return None

    times = sorted(part_df["取得時刻表示"].unique().tolist())

    rows = []

    for job, job_df in part_df.groupby("職業"):
        for start, start_df in job_df.groupby("開始"):
            start_df = start_df.sort_values("取得時刻_dt")

            values = {}

            for _, row in start_df.iterrows():
                values[row["取得時刻表示"]] = int(row["残席"])

            rows.append({
                "job": job,
                "start": start,
                "end": str(start_df["終了"].iloc[0]),
                "capacity": int(start_df["定員"].max()),
                "values": values
            })

    rows = sorted(rows, key=lambda x: (x["job"], x["start"]))

    updated_at = part_df["取得時刻_dt"].max().strftime("%Y/%m/%d %H:%M")

    return {
        "label": label,
        "updated_at": updated_at,
        "times": times,
        "rows": rows,
        "pivot": {
            "times": times,
            "rows": rows
        }
    }


def make_dates_data(df):
    dates = {}

    for date, day_df in df.groupby("日付"):
        day_df = day_df.copy()

        parts = {}

        part1 = make_part_data(day_df, "part1")
        part2 = make_part_data(day_df, "part2")

        if part1:
            parts["part1"] = part1

        if part2:
            parts["part2"] = part2

        dates[date] = {
            "updated_at": day_df["取得時刻_dt"].max().strftime("%Y/%m/%d %H:%M"),
            "parts": parts
        }

    return dates


def make_weekly_ranking(df, top_n=10):
    df = df.copy()

    latest = df["取得時刻_dt"].max()
    start_date = latest - pd.Timedelta(days=7)
    df = df[df["取得時刻_dt"] >= start_date]

    if df.empty:
        return []

    df["残席率"] = df["残席"] / df["定員"]

    results = []

    for job, g in df.groupby("職業"):
        g = g.copy()

        avg_remaining_rate = g["残席率"].mean()
        remaining_score = 1 - avg_remaining_rate

        soldout_count = 0
        total_slots = 0
        speed_scores = []
        capacities = []

        for _, sg in g.groupby(["日付", "開始"]):
            sg = sg.sort_values("取得時刻_dt")

            total_slots += 1
            capacity = sg["定員"].max()
            capacities.append(capacity)

            soldout_rows = sg[sg["残席"] <= 0]

            if not soldout_rows.empty:
                soldout_count += 1

                first_soldout_time = soldout_rows["取得時刻_dt"].min()

                start_dt = pd.to_datetime(
                    sg["日付"].iloc[0] + " " + str(sg["開始"].iloc[0]),
                    errors="coerce"
                )

                if pd.notna(start_dt):
                    minutes_until_start = (start_dt - first_soldout_time).total_seconds() / 60
                    speed_score = (minutes_until_start + 30) / 120
                    speed_score = max(0, min(1, speed_score))
                else:
                    speed_score = 0

                speed_scores.append(speed_score)
            else:
                speed_scores.append(0)

        avg_speed_score = sum(speed_scores) / len(speed_scores) if speed_scores else 0
        soldout_rate = soldout_count / total_slots if total_slots else 0
        avg_capacity = sum(capacities) / len(capacities) if capacities else 1

        if avg_capacity <= 1:
            capacity_bonus = 0.92
        elif avg_capacity <= 3:
            capacity_bonus = 0.97
        elif avg_capacity <= 5:
            capacity_bonus = 1.00
        else:
            capacity_bonus = 1.05

        popularity_score = (
            remaining_score * 0.50 +
            avg_speed_score * 0.30 +
            soldout_rate * 0.20
        ) * capacity_bonus

        results.append({
            "job": job,
            "score": popularity_score
        })

    ranking = sorted(results, key=lambda x: x["score"], reverse=True)

    return [
        {
            "rank": i + 1,
            "job": item["job"]
        }
        for i, item in enumerate(ranking[:top_n])
    ]


def main():
    df = load_all_csv()
    df = clean_df(df)

    dates = make_dates_data(df)
    weekly_ranking = make_weekly_ranking(df, top_n=10)

    data = {
        "dates": dates,
        "weekly_ranking": weekly_ranking
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"OK: {OUTPUT_JSON} を作成しました")
    print("週間ランキング:")
    for item in weekly_ranking:
        print(f'{item["rank"]}位 {item["job"]}')


if __name__ == "__main__":
    main()