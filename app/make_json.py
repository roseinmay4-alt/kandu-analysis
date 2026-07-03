import json
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"
DOCS_DIR = BASE_DIR / "docs"

# 最新CSVを取得
csv_files = sorted(RAW_DIR.glob("*.csv"))
if not csv_files:
    print("CSVがありません")
    exit()

latest = csv_files[-1]

df = pd.read_csv(latest)

# ランキング（残席が少ないほど人気）
ranking = (
    df.groupby("職業")["残席"]
    .sum()
    .sort_values()
    .reset_index()
)

ranking_list = []

for i, row in ranking.head(10).iterrows():
    ranking_list.append({
        "rank": i + 1,
        "name": row["職業"],
        "score": int(row["残席"])
    })

# JSON作成
data = {
    "updated": str(df["取得時刻"].iloc[0]),
    "ranking": ranking_list,
    "activities": df.to_dict(orient="records")
}

with open(DOCS_DIR / "data.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("docs/data.json を更新しました！")