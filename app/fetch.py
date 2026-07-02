import requests
import pandas as pd
from datetime import datetime
from pathlib import Path

URL = "https://sp.kandu-kidsdream.com/api/signage/get-signage-api"

HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://sp.kandu-kidsdream.com/",
}

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def make_filename(api_timestamp: str) -> Path:
    file_timestamp = (
        api_timestamp
        .replace("/", "")
        .replace(":", "")
        .replace(" ", "_")
    )
    return RAW_DIR / f"kandu_{file_timestamp}.csv"


def main():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    print("ステータスコード:", r.status_code)
    r.raise_for_status()

    data = r.json()

    api_timestamp = data.get("response_information", {}).get("timestamp")
    if not api_timestamp:
        api_timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    response_data = data.get("response_data", [])

    if not response_data:
        message = data.get("response_information", {}).get("message", "")
        print("対象データがありません。営業時間外か、予約データが空です。")
        print("APIメッセージ:", message)
        return

    rows = []

    for activity in response_data:
        name = activity.get("activity_name_ruby", "")
        capacity = activity.get("possible_number", "")

        for slot in activity.get("reservation_possibles", []):
            start_text = slot.get("start_time", "")
            end_text = slot.get("end_time", "")

            duration = ""
            if start_text and end_text:
                start = datetime.strptime(start_text, "%H:%M")
                end = datetime.strptime(end_text, "%H:%M")
                duration = int((end - start).total_seconds() / 60) + 1

            rows.append({
                "取得時刻": api_timestamp,
                "職業": name,
                "定員": capacity,
                "開始": start_text,
                "終了": end_text,
                "体験時間": duration,
                "残席": slot.get("reservation_count", ""),
            })

    if not rows:
        print("アクティビティはありましたが、予約枠データがありませんでした。")
        return

    df = pd.DataFrame(rows)
    filename = make_filename(api_timestamp)
    df.to_csv(filename, index=False, encoding="utf-8-sig")

    print(f"{filename} に {len(df)}件 保存しました")
    print(df.head())


if __name__ == "__main__":
    main()