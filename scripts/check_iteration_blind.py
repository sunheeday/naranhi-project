"""평가 산출물에 모델·백엔드 이름이 새어나갔는지 검사한다. CI/게이트용.

평가자는 어느 arm 이 어느 모델인지 몰라야 한다. arms.json 은 검사 대상에서 제외한다
(그 파일이 매핑을 보관하는 자리이고, 평가자는 읽지 않기로 되어 있다).
"""
import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

FORBIDDEN = ("gemini", "vertex", "nova", "claude", "bedrock", "anthropic", "amazon")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iter-dir", required=True, type=Path)
    args = parser.parse_args()

    targets = sorted((args.iter_dir / "evaluation").rglob("*.md"))
    targets += sorted((args.iter_dir / "evaluation").rglob("*.json"))
    if not targets:
        print(f"ERROR: 평가 산출물이 없다: {args.iter_dir / 'evaluation'}", file=sys.stderr)
        return 2

    failed = False
    for path in targets:
        lowered = path.read_text(encoding="utf-8", errors="replace").lower()
        hits = [word for word in FORBIDDEN if word in lowered]
        if hits:
            print(f"블라인드 위반 {path}: {', '.join(hits)}")
            failed = True

    if failed:
        print("\n블라인드 검사 실패 — 평가자가 모델 정체를 알고 있었다는 뜻이다.")
        return 1

    print(f"평가 산출물 {len(targets)}개, 모델명 노출 0건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
