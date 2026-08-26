"""supabase/migrations/ 의 번호 접두가 중복되는지 검사한다. CI 용."""
import re
import sys
from collections import defaultdict
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / "supabase" / "migrations"
PATTERN = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

by_number = defaultdict(list)
bad_names = []

for path in sorted(MIGRATIONS.glob("*.sql")):
    m = PATTERN.match(path.name)
    if not m:
        bad_names.append(path.name)
        continue
    by_number[m.group(1)].append(path.name)

failed = False

for name in bad_names:
    print(f"이름 규칙 위반: {name} (형식: NNNN_snake_case.sql)")
    failed = True

for number, names in sorted(by_number.items()):
    if len(names) > 1:
        print(f"번호 중복 {number}: {', '.join(names)}")
        failed = True

if failed:
    print("\n마이그레이션 번호 검사 실패")
    sys.exit(1)

print(f"마이그레이션 {sum(len(v) for v in by_number.values())}개, 번호 중복 없음")
