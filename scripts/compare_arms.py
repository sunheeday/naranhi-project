"""두 arm 의 파이프라인 산출물을 비교해 게이트 G1·G4·G5 를 판정한다.

G1  validation.hard_fact 통과율이 기준선 대비 하락 0건
G4  final_translation 에 placeholder({{...}}) 잔존 0건
G5  wall_seconds 중앙값이 기준선보다 낮다

G2(평가자 verdict)·G3(8축 평균)는 평가자 에이전트 산출물로 사람이 판정한다.
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def collect(iter_dir: Path, arm: str) -> dict:
    out = {}
    for path in sorted(iter_dir.glob(f"notices/*/*/pipeline-output/{arm}/*.json")):
        notice_id = path.parent.parent.parent.name
        out[(notice_id, path.stem)] = json.loads(path.read_text(encoding="utf-8"))
    return out


def status(result: dict, axis: str) -> str | None:
    return ((result.get("validation") or {}).get(axis) or {}).get("status")


def median_wall(results: dict) -> float | None:
    values = [
        r.get("wall_seconds") for r in results.values()
        if isinstance(r.get("wall_seconds"), (int, float))
    ]
    return round(statistics.median(values), 1) if values else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iter-dir", required=True, type=Path)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--arm", required=True)
    args = parser.parse_args()

    base = collect(args.iter_dir, args.baseline)
    cand = collect(args.iter_dir, args.arm)
    shared = sorted(set(base) & set(cand))
    if not shared:
        print("ERROR: 두 arm 의 공통 산출물이 없다", file=sys.stderr)
        return 2
    print(f"비교 대상 {len(shared)}건 ({args.baseline} vs {args.arm})")

    hard_fact_reg = [
        k for k in shared
        if status(base[k], "hard_fact") == "passed" and status(cand[k], "hard_fact") != "passed"
    ]
    tone_reg = [
        k for k in shared
        if status(base[k], "context_tone") == "passed" and status(cand[k], "context_tone") != "passed"
    ]
    placeholders = [k for k in shared if "{{" in str(cand[k].get("final_translation") or "")]
    parse_errors = [k for k in shared if cand[k].get("status") == "driver_error"]
    base_med, cand_med = median_wall(base), median_wall(cand)

    print(f"G1 hard_fact 하락      : {len(hard_fact_reg)}건 {hard_fact_reg[:5]}")
    print(f"   context_tone 하락   : {len(tone_reg)}건 (참고 — G3 판단 재료)")
    print(f"G4 placeholder 잔존    : {len(placeholders)}건 {placeholders[:5]}")
    print(f"   driver_error(파싱 등): {len(parse_errors)}건 {parse_errors[:5]}")
    print(f"G5 wall_seconds 중앙값 : {base_med}s → {cand_med}s")

    ok = (
        not hard_fact_reg
        and not placeholders
        and not parse_errors
        and base_med is not None
        and cand_med is not None
        and cand_med < base_med
    )
    print("\nG1/G4/G5:", "통과" if ok else "실패")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
