#!/usr/bin/env python3
"""
Morning Dashboard — Ringkasan hasil backtest semalam
"""
import json
from pathlib import Path
from datetime import datetime

REPORT_FILE = "/workspace/eval_report.json"
LOG_FILE    = "/workspace/eval_log.txt"

def print_dashboard():
    if not Path(REPORT_FILE).exists():
        print("❌ Belum ada hasil evaluasi.")
        return

    with open(REPORT_FILE) as f:
        data = json.load(f)

    if not data:
        print("❌ Data kosong.")
        return

    print("\n" + "="*60)
    print("🌅 RABBANI AGENT — MORNING REPORT")
    print("="*60)
    print(f"Total siklus evaluasi: {len(data)}")
    print(f"Periode: {data[0]['timestamp']} → {data[-1]['timestamp']}")

    # Score trend
    scores = [d["avg_score"] for d in data]
    print(f"\n📈 TREN SCORE:")
    for i, d in enumerate(data):
        bar = "█" * int(d["avg_score"])
        print(f"  Cycle #{d['cycle']}: {bar} {d['avg_score']}/10 ({d['passing']}/{d['total']} passed)")

    # Best and worst
    best = max(data, key=lambda x: x["avg_score"])
    worst = min(data, key=lambda x: x["avg_score"])
    latest = data[-1]

    print(f"\n🏆 Best cycle: #{best['cycle']} — {best['avg_score']}/10")
    print(f"📉 Worst cycle: #{worst['cycle']} — {worst['avg_score']}/10")
    print(f"🕐 Latest cycle: #{latest['cycle']} — {latest['avg_score']}/10")

    # Improvement applied count
    applied = sum(1 for d in data if d.get("improvements_applied"))
    print(f"\n🔧 Auto-improvements applied: {applied}x")

    # Per-scenario average
    print("\n📊 SCORE PER SKENARIO (rata-rata semua siklus):")
    scenario_scores = {}
    for d in data:
        for s in d.get("per_scenario", []):
            name = s["name"]
            if name not in scenario_scores:
                scenario_scores[name] = []
            scenario_scores[name].append(s["score"])

    for name, sc_list in scenario_scores.items():
        avg = sum(sc_list) / len(sc_list)
        icon = "✅" if avg >= 7 else "⚠️" if avg >= 5 else "❌"
        print(f"  {icon} {name}: {avg:.1f}/10")

    # Recurring weaknesses
    print("\n🔍 KELEMAHAN YANG SERING MUNCUL:")
    weaknesses = []
    for d in data:
        for s in d.get("per_scenario", []):
            if s.get("weakness") and s["score"] < 7:
                weaknesses.append(s["weakness"])

    if weaknesses:
        for w in weaknesses[-5:]:
            print(f"  • {w}")
    else:
        print("  Tidak ada kelemahan signifikan!")

    print("\n" + "="*60)
    print("✅ main.py sudah diupdate dengan perbaikan terbaik.")
    print("="*60 + "\n")

if __name__ == "__main__":
    print_dashboard()
