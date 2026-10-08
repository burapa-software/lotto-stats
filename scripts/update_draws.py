"""เพิ่มผลเลขท้าย 2 ตัวงวดล่าสุดลงใน data/draws.csv

วิธีใช้
  python scripts/update_draws.py                       ดึงผลล่าสุดจากเว็บกองสลาก (GLO) อัตโนมัติ
  python scripts/update_draws.py --date 2026-10-16 --last2 57   ใส่ผลเองด้วยมือ (วันที่เป็น ค.ศ.)

ไฟล์จะถูกแก้เฉพาะเมื่อได้งวดที่ใหม่กว่างวดล่าสุดในไฟล์ ถ้าไม่มีอะไรใหม่ก็จบเฉยๆ
ใช้แค่ไลบรารีมาตรฐานของ Python ไม่ต้องติดตั้งอะไรเพิ่ม
"""
import argparse
import csv
import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "draws.csv"
GLO_LATEST = "https://www.glo.or.th/api/lottery/getLatestLottery"
TZ = dt.timezone(dt.timedelta(hours=7))  # เวลาไทย


def read_rows():
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        return [(r["date"], r["last2"]) for r in csv.DictReader(f)]


def write_rows(rows):
    rows = sorted(set(rows))
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "last2"])
        w.writerows(rows)


def find_key(obj, key):
    """ค้นหา key ในโครงสร้าง JSON ทุกชั้น คืนค่าตัวแรกที่เจอ"""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        obj = list(obj.values())
    if isinstance(obj, list):
        for v in obj:
            found = find_key(v, key)
            if found is not None:
                return found
    return None


def fetch_glo():
    """ดึงงวดล่าสุดจาก API ของกองสลาก คืน (วันที่ ค.ศ. YYYY-MM-DD, เลขสองหลัก)"""
    req = urllib.request.Request(
        GLO_LATEST,
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 lotto-stats"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)

    last2 = find_key(data, "last2")
    number = None
    if isinstance(last2, dict):
        nums = last2.get("number")
        if isinstance(nums, list) and nums:
            number = nums[0].get("value") if isinstance(nums[0], dict) else nums[0]
        elif isinstance(nums, (str, int)):
            number = nums
    date = find_key(data, "date")

    number = str(number or "").strip()
    date = str(date or "").strip()[:10]
    if not re.fullmatch(r"\d{2}", number):
        raise ValueError(f"อ่านเลขท้าย 2 ตัวจาก API ไม่ได้ (ได้ค่า {number!r})")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError(f"อ่านวันที่งวดจาก API ไม่ได้ (ได้ค่า {date!r})")
    year = int(date[:4])
    if year > 2400:  # API ส่งปี พ.ศ. มา
        date = f"{year - 543}{date[4:]}"
    return date, number


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="วันที่งวด ค.ศ. เช่น 2026-10-16")
    ap.add_argument("--last2", help="เลขท้าย 2 ตัว เช่น 57")
    args = ap.parse_args()

    rows = read_rows()
    latest = max(d for d, _ in rows)

    if args.date or args.last2:
        if not (args.date and args.last2):
            sys.exit("ต้องใส่ทั้ง --date และ --last2")
        date, number = args.date.strip(), args.last2.strip().zfill(2)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or not re.fullmatch(r"\d{2}", number):
            sys.exit("รูปแบบไม่ถูกต้อง: --date ต้องเป็น YYYY-MM-DD (ค.ศ.) และ --last2 เป็นเลข 2 หลัก")
        source = "ใส่เอง"
    else:
        try:
            date, number = fetch_glo()
        except Exception as e:  # ไม่ทำให้ workflow ล้ม แค่บันทึกไว้ใน log
            print(f"ดึงผลอัตโนมัติไม่สำเร็จ: {e}")
            print("ใส่ผลเองได้ที่แท็บ Actions > Update lottery stats > Run workflow")
            return
        source = "GLO"

    today = dt.datetime.now(TZ).date().isoformat()
    if date > today:
        sys.exit(f"วันที่ {date} อยู่ในอนาคต ไม่บันทึก")

    existing = dict(rows)
    if date in existing:
        if existing[date] == number:
            print(f"งวด {date} มีอยู่แล้ว ({number}) ไม่มีอะไรต้องอัปเดต")
            return
        if source != "ใส่เอง":
            print(f"งวด {date} ในไฟล์เป็น {existing[date]} แต่ API ได้ {number} ไม่แก้ทับอัตโนมัติ")
            return
        print(f"แก้งวด {date} จาก {existing[date]} เป็น {number}")
        rows = [(d, number if d == date else n) for d, n in rows]
    elif date < latest and source != "ใส่เอง":
        print(f"API ส่งงวด {date} ซึ่งเก่ากว่างวดล่าสุดในไฟล์ ({latest}) ข้าม")
        return
    else:
        rows.append((date, number))
        print(f"เพิ่มงวด {date}: {number} (จาก{source})")

    write_rows(rows)


if __name__ == "__main__":
    main()
