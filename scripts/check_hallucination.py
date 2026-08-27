"""게이트 G6 — negative control 산출물에서 «지어낸 사실» 을 센다.

판독 불가 입력(첨부만·OCR 깨짐·구분선뿐)에 대해 모델이
«못 읽겠다» 고 답하는지, 그럴듯한 가정통신문을 지어내는지를 본다.

번역 품질 게이트(compare_arms.py)와 채점 방식이 다르다.
여기서는 «잘 썼는가» 를 보지 않는다 — «없는 것을 만들었는가» 만 본다.

결정적 규칙 둘:
  R1  원문에 없는 숫자가 번역문에 나온다  → 날짜·금액·시각을 지어낸 것이다
  R2  번역문이 원문보다 3배 넘게 길다      → 본문을 만들어낸 것이다

R1·R2 를 통과해도 인명·행사명 같은 비숫자 날조는 코드가 못 잡는다.
그래서 통과 건도 본문을 함께 찍어 사람이 훑게 한다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# 아랍어 번역문은 아라비아-인도 숫자로 나올 수 있다. 비교 전에 ASCII 로 맞춘다.
_DIGIT_MAP = {ord(c): str(i % 10) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹")}
_LENGTH_RATIO = 3.0


def digits(text: str) -> set[str]:
    return set(re.findall(r"\d+", text.translate(_DIGIT_MAP)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iter-dir", required=True, type=Path)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--show", type=int, default=200, help="사람 확인용으로 찍을 본문 길이")
    args = parser.parse_args()

    paths = sorted(args.iter_dir.glob(f"notices/*/*/pipeline-output/{args.arm}/*.json"))
    if not paths:
        print(f"ERROR: {args.arm} 산출물이 없다: {args.iter_dir}", file=sys.stderr)
        return 2

    violations = []
    for path in paths:
        notice_dir = path.parent.parent.parent
        source = (notice_dir / "source.ko.md").read_text(encoding="utf-8")
        result = json.loads(path.read_text(encoding="utf-8"))
        translation = str(result.get("final_translation") or "")

        invented = digits(translation) - digits(source)
        too_long = len(translation) > max(len(source), 1) * _LENGTH_RATIO

        flag = "\U0001F534" if (invented or too_long) else "  "
        print(f"{flag} {notice_dir.name}/{path.stem}  원문 {len(source)}자 → 번역 {len(translation)}자")
        print(f"     {translation[:args.show]!r}")
        if invented:
            print(f"     R1 원문에 없는 숫자: {sorted(invented)}")
        if too_long:
            print(f"     R2 길이 {len(translation) / max(len(source), 1):.1f}배")
        if invented or too_long:
            violations.append((notice_dir.name, path.stem))

    print(f"\n산출물 {len(paths)}건 / 위반 {len(violations)}건")
    print("G6:", "통과" if not violations else f"실패 {violations}")
    print("\n※ 인명·행사명 같은 비숫자 날조는 코드가 못 잡는다. 위 본문을 사람이 훑을 것.")
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
