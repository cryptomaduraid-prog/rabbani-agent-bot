#!/usr/bin/env python3
"""
Rabbani Agent — Continuous Backtest & Evaluation Loop
Runs every 2 hours, improves main.py iteratively, saves reports.
"""

import os, json, re, time, sys
from datetime import datetime
from pathlib import Path
import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
REPORT_FILE  = "/workspace/eval_report.json"
MAIN_FILE    = "/workspace/main.py"
LOG_FILE     = "/workspace/eval_log.txt"

# ─── TEST SCENARIOS ─────────────────────────────────────────────────────────
TEST_SCENARIOS = [
    # (scenario_name, conversation_turns, expected_qualities)
    {
        "name": "Topic Continuity — Crypto",
        "turns": [
            {"role": "user", "content": "jelasin tentang bitcoin halving"},
            {"role": "user", "content": "trus dampaknya ke altcoin gimana?"},
            {"role": "user", "content": "yang paling untung biasanya altcoin apa?"},
        ],
        "expected": ["ingat konteks bitcoin halving", "jawab tentang altcoin", "berikan rekomendasi spesifik"],
        "checks": ["topic_continuity", "specificity", "no_reset"]
    },
    {
        "name": "Topic Switch Detection",
        "turns": [
            {"role": "user", "content": "bitcoin lagi bullish banget sekarang"},
            {"role": "user", "content": "eh, buatin gue twitter thread tentang NFT dong"},
        ],
        "expected": ["detect topik baru", "buat twitter thread", "tidak campur konteks bitcoin"],
        "checks": ["topic_switch", "task_execution", "clean_context"]
    },
    {
        "name": "Follow-up Elaboration",
        "turns": [
            {"role": "user", "content": "apa itu DeFi?"},
            {"role": "user", "content": "elaborasi lebih dong"},
            {"role": "user", "content": "kasih contoh konkret"},
        ],
        "expected": ["elaborasi DeFi lebih dalam", "berikan contoh nyata", "tidak mengulang perkenalan"],
        "checks": ["elaboration_depth", "no_repetition", "context_memory"]
    },
    {
        "name": "Real-time Info Request",
        "turns": [
            {"role": "user", "content": "harga bitcoin sekarang berapa?"},
        ],
        "expected": ["tidak bilang tidak tahu", "berikan konteks harga", "natural tanpa sebut googling"],
        "checks": ["no_refuse", "natural_tone", "no_search_mention"]
    },
    {
        "name": "Content Creation",
        "turns": [
            {"role": "user", "content": "buatin caption instagram buat launch token baru"},
        ],
        "expected": ["ada hook", "ada body dengan emoji", "ada hashtag", "ada CTA"],
        "checks": ["has_hook", "has_hashtags", "has_cta", "professional_tone"]
    },
    {
        "name": "Critical Analysis",
        "turns": [
            {"role": "user", "content": "analisis kritis tentang meme coin"},
        ],
        "expected": ["ada fakta", "ada perspektif pro dan kontra", "ada kesimpulan actionable"],
        "checks": ["balanced_view", "has_data", "actionable_conclusion"]
    },
    {
        "name": "Bahasa Indonesia Natural",
        "turns": [
            {"role": "user", "content": "bro, gue bingung sama konsep staking. jelasin dong santai"],
        ],
        "expected": ["bahasa santai", "pakai gue/kamu bukan saya/anda", "mudah dipahami"],
        "checks": ["informal_language", "no_formal_pronouns", "clarity"]
    },
    {
        "name": "Multi-topic Session",
        "turns": [
            {"role": "user", "content": "ethereum gas fee lagi mahal banget"},
            {"role": "user", "content": "ada solusi ga?"},
            {"role": "user", "content": "oke makasih, ntar lagi ya"},
            {"role": "user", "content": "eh btw, buatin thread twitter tentang layer 2"},
        ],
        "expected": ["jawab tentang gas fee", "berikan solusi konkret", "detect topic switch ke L2", "buat thread baru"],
        "checks": ["problem_solving", "topic_detection", "fresh_task"]
    }
]

# ─── LLM CALL ───────────────────────────────────────────────────────────────
def call_groq(messages, model="llama-3.3-70b-versatile", temperature=0.0, max_tokens=1500):
    if not GROQ_API_KEY:
        return None
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"

def get_system_prompt(topic="crypto umum"):
    return f"""Kamu adalah Rabbani — AI Agent cerdas, kritis, dan natural untuk crypto/Web3.

KEPRIBADIAN:
- Ngobrol natural seperti teman yang expert, BUKAN robot kaku
- Bahasa Indonesia santai tapi berbobot (pakai gue/kamu)
- Proaktif suggest langkah berikutnya
- Ingat konteks sebelumnya, jangan reset topik tanpa alasan

TOPIK AKTIF: {topic}

Jawab secara natural, lanjutkan konteks yang ada."""

# ─── SIMULATE CONVERSATION ──────────────────────────────────────────────────
def simulate_conversation(scenario: dict) -> dict:
    """Simulate multi-turn conversation and collect bot responses."""
    history = []
    responses = []
    topic = "umum"

    system = get_system_prompt(topic)

    for i, turn in enumerate(scenario["turns"]):
        user_msg = turn["content"]

        # Build message list for this turn
        messages = [{"role": "system", "content": system}]
        for h in history:
            messages.append(h)
        messages.append({"role": "user", "content": user_msg})

        # Get response
        bot_resp = call_groq(messages, temperature=0.7, max_tokens=800)
        if not bot_resp or bot_resp.startswith("ERROR"):
            responses.append({"turn": i+1, "user": user_msg, "bot": bot_resp or "NO_RESPONSE", "error": True})
            continue

        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": bot_resp})
        responses.append({"turn": i+1, "user": user_msg, "bot": bot_resp, "error": False})

    return {"scenario": scenario["name"], "responses": responses}

# ─── LLM AS JUDGE ───────────────────────────────────────────────────────────
def judge_response(scenario: dict, sim_result: dict) -> dict:
    """Use LLM to score the conversation quality."""
    checks = scenario["checks"]
    expected = scenario["expected"]
    conversation_text = ""
    for r in sim_result["responses"]:
        conversation_text += f"User: {r['user']}\nRabbani: {r['bot']}\n\n"

    judge_prompt = f"""Kamu adalah evaluator AI yang ketat. Nilai percakapan bot berikut.

SKENARIO: {scenario["name"]}
EKSPEKTASI:
{chr(10).join(f"- {e}" for e in expected)}

PERCAKAPAN:
{conversation_text[:3000]}

Nilai setiap aspek berikut (0-10) dan berikan alasan singkat:
{chr(10).join(f"- {c}" for c in checks)}

Juga berikan:
- overall_score (0-10): rata-rata keseluruhan
- main_weakness: kelemahan utama yang perlu diperbaiki (1 kalimat)
- improvement_suggestion: saran konkret untuk memperbaiki kode/prompt (1-2 kalimat)

Jawab HANYA dalam JSON:
{{
  "scores": {{{", ".join(f'"{c}": {{"score": X, "reason": "..."}}' for c in checks)}}},
  "overall_score": X,
  "main_weakness": "...",
  "improvement_suggestion": "..."
}}"""

    result_raw = call_groq(
        [{"role": "user", "content": judge_prompt}],
        model="llama-3.1-8b-instant",
        temperature=0.0,
        max_tokens=1000
    )

    try:
        if "```" in result_raw:
            result_raw = result_raw.split("```")[1].replace("json","").strip()
        return json.loads(result_raw)
    except:
        return {"overall_score": 0, "main_weakness": "Parse error", "improvement_suggestion": "N/A", "scores": {}}

# ─── IMPROVEMENT ENGINE ─────────────────────────────────────────────────────
def generate_improvements(all_eval_results: list) -> str:
    """Analyze all weaknesses and generate code/prompt improvements."""
    weaknesses = []
    suggestions = []
    low_scores = []

    for result in all_eval_results:
        score = result.get("judge", {}).get("overall_score", 10)
        weakness = result.get("judge", {}).get("main_weakness", "")
        suggestion = result.get("judge", {}).get("improvement_suggestion", "")
        scenario = result.get("scenario", "")

        if score < 7:
            low_scores.append(f"Skenario '{scenario}': score {score}/10")
        if weakness:
            weaknesses.append(weakness)
        if suggestion:
            suggestions.append(suggestion)

    if not weaknesses:
        return "Semua skenario di atas threshold. Tidak ada perubahan diperlukan."

    improvement_prompt = f"""Kamu adalah senior AI engineer. Analisis kelemahan bot Telegram berikut dan buat perbaikan konkret.

SKOR RENDAH:
{chr(10).join(low_scores) if low_scores else "Tidak ada"}

KELEMAHAN TERIDENTIFIKASI:
{chr(10).join(f"- {w}" for w in weaknesses)}

SARAN YANG SUDAH ADA:
{chr(10).join(f"- {s}" for s in suggestions)}

SYSTEM PROMPT SAAT INI (bagian utama):
Kamu adalah Rabbani — AI Agent cerdas, kritis, dan natural untuk crypto/Web3.
KEPRIBADIAN: Ngobrol natural seperti teman yang expert, Bahasa Indonesia santai (gue/kamu), Proaktif suggest...

Berikan:
1. PERBAIKAN SYSTEM PROMPT: tulis ulang bagian yang perlu diperbaiki
2. PERBAIKAN LOGIKA: pseudocode atau penjelasan perubahan logika
3. PRIORITAS: urutkan perbaikan dari yang paling impactful

Format: plain text, detail tapi ringkas."""

    return call_groq(
        [{"role": "user", "content": improvement_prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.3,
        max_tokens=1500
    )

# ─── APPLY IMPROVEMENTS ─────────────────────────────────────────────────────
def apply_prompt_improvements(improvements: str, all_results: list) -> bool:
    """
    Auto-apply improvements to SYSTEM_PROMPT in main.py
    based on evaluation findings.
    """
    if not improvements or improvements.startswith("ERROR"):
        return False

    # Compute average score
    scores = [r.get("judge", {}).get("overall_score", 0) for r in all_results]
    avg_score = sum(scores) / len(scores) if scores else 0

    with open(MAIN_FILE, "r") as f:
        code = f.read()

    # Build new system prompt based on findings
    prompt_gen = f"""Kamu adalah AI prompt engineer. Tulis ulang SYSTEM_PROMPT untuk bot Telegram Rabbani.

ANALISIS EVALUASI (rata-rata score: {avg_score:.1f}/10):
{improvements[:2000]}

SYSTEM_PROMPT SAAT INI:
```
SYSTEM_PROMPT = \"\"\"Kamu adalah Rabbani — AI Agent cerdas, kritis, dan natural untuk crypto/Web3.

KEPRIBADIAN:
- Ngobrol natural seperti teman yang expert, BUKAN robot kaku
- Bahasa Indonesia santai tapi berbobot
- Proaktif suggest langkah berikutnya
- Jika topik belum selesai, lanjutkan benang merahnya — jangan tiba-tiba reset
- Kalau user minta elaborasi/lanjut, kamu INGAT konteks sebelumnya dengan tepat

CARA KERJA:
- Sudah ada data real-time jika dibutuhkan (disisipkan dalam konteks)
- Jangan pernah sebut "saya mencari di internet" atau "berdasarkan pencarian saya" — langsung saja
- Jawab seperti kamu memang tahu, bukan seperti sedang googling
- Jika ada data baru dari web, blend naturally ke dalam jawaban
```

Tulis HANYA string isi system prompt yang baru (tanpa triple-quote, tanpa prefix SYSTEM_PROMPT =).
Pertahankan placeholder: {{topic}}, {{search_data}}, {{history}}, {{message}}
Perbaiki berdasarkan temuan evaluasi. Bahasa Indonesia."""

    new_prompt_content = call_groq(
        [{"role": "user", "content": prompt_gen}],
        model="llama-3.3-70b-versatile",
        temperature=0.3,
        max_tokens=1000
    )

    if not new_prompt_content or new_prompt_content.startswith("ERROR"):
        return False

    # Find and replace SYSTEM_PROMPT in code
    start_marker = 'SYSTEM_PROMPT = """'
    end_marker = 'TOPIK AKTIF: {topic}'

    start_idx = code.find(start_marker)
    end_marker2 = '"""\n\n# ─── CORE'
    end_idx = code.find(end_marker2)

    if start_idx == -1 or end_idx == -1:
        return False

    new_code = code[:start_idx] + f'SYSTEM_PROMPT = """\n{new_prompt_content}\n' + code[end_idx:]

    with open(MAIN_FILE, "w") as f:
        f.write(new_code)

    return True

# ─── MAIN EVAL LOOP ─────────────────────────────────────────────────────────
def run_evaluation_cycle(cycle_num: int) -> dict:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"🔬 BACKTEST CYCLE #{cycle_num} — {timestamp}")
    print(f"{'='*60}")

    all_results = []

    for scenario in TEST_SCENARIOS:
        print(f"  ▶ Testing: {scenario['name']}...", end=" ", flush=True)

        # Simulate conversation
        sim = simulate_conversation(scenario)

        # Judge the response
        judge = judge_response(scenario, sim)

        score = judge.get("overall_score", 0)
        result = {
            "scenario": scenario["name"],
            "simulation": sim,
            "judge": judge,
            "timestamp": timestamp,
            "cycle": cycle_num
        }
        all_results.append(result)

        status = "✅" if score >= 7 else "⚠️" if score >= 5 else "❌"
        print(f"{status} Score: {score}/10")

    # Overall stats
    scores = [r["judge"].get("overall_score", 0) for r in all_results]
    avg = sum(scores) / len(scores) if scores else 0
    passing = sum(1 for s in scores if s >= 7)

    print(f"\n📊 HASIL: {passing}/{len(scores)} passed | Avg: {avg:.1f}/10")

    # Generate improvements if below threshold
    improvements = ""
    applied = False
    if avg < 7.5:
        print("🔧 Generating improvements...")
        improvements = generate_improvements(all_results)
        if improvements and not improvements.startswith("ERROR"):
            applied = apply_prompt_improvements(improvements, all_results)
            print(f"{'✅ Improvements applied to main.py' if applied else '📝 Improvements logged only'}")
    else:
        print("✨ Performance good — no changes needed this cycle")

    return {
        "cycle": cycle_num,
        "timestamp": timestamp,
        "avg_score": round(avg, 2),
        "passing": passing,
        "total": len(scores),
        "per_scenario": [
            {
                "name": r["scenario"],
                "score": r["judge"].get("overall_score", 0),
                "weakness": r["judge"].get("main_weakness", ""),
                "suggestion": r["judge"].get("improvement_suggestion", "")
            }
            for r in all_results
        ],
        "improvements_generated": bool(improvements),
        "improvements_applied": applied,
        "improvement_notes": improvements[:800] if improvements else ""
    }

# ─── ENTRY POINT ────────────────────────────────────────────────────────────
def main():
    cycle_num = 1

    # Load existing report to continue from last cycle
    if Path(REPORT_FILE).exists():
        try:
            with open(REPORT_FILE, "r") as f:
                existing = json.load(f)
            if isinstance(existing, list) and existing:
                cycle_num = existing[-1].get("cycle", 0) + 1
        except:
            pass
    else:
        existing = []

    print(f"\n🤖 Rabbani Agent Backtest — Starting Cycle #{cycle_num}")
    print(f"📁 Report: {REPORT_FILE}")
    print(f"🔑 API: {'✅ GROQ_API_KEY found' if GROQ_API_KEY else '❌ No GROQ_API_KEY — using mock mode'}")

    result = run_evaluation_cycle(cycle_num)

    # Append to report
    if isinstance(existing, list):
        existing.append(result)
    else:
        existing = [result]

    with open(REPORT_FILE, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    # Write human-readable log
    with open(LOG_FILE, "a") as f:
        f.write(f"\n{'='*50}\n")
        f.write(f"CYCLE #{result['cycle']} — {result['timestamp']}\n")
        f.write(f"Score: {result['avg_score']}/10 | Passed: {result['passing']}/{result['total']}\n")
        for s in result["per_scenario"]:
            icon = "✅" if s["score"] >= 7 else "⚠️" if s["score"] >= 5 else "❌"
            f.write(f"  {icon} {s['name']}: {s['score']}/10\n")
            if s["weakness"]:
                f.write(f"     Weakness: {s['weakness']}\n")
        if result["improvements_applied"]:
            f.write(f"🔧 IMPROVEMENTS APPLIED TO main.py\n")
        f.write(f"{'='*50}\n")

    print(f"\n💾 Report saved → {REPORT_FILE}")
    print(f"📋 Log saved → {LOG_FILE}")
    print(f"✅ Cycle #{cycle_num} complete!\n")

if __name__ == "__main__":
    main()
