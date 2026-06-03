from __future__ import annotations

import asyncio
import unittest

from app.services.refinement_service import (
    _promote_section_headings,
    _squeeze_spaces,
    _strip_board_meta,
    degenerate,
    light_clean,
    mask,
    refine,
    unmask,
)


class BoardMetaStripTests(unittest.TestCase):
    def test_strips_board_metadata_lines(self) -> None:
        src = "# 6월 진로 특강\n작성자 김**\n작성일 2026-05-28\n조회수 37\n댓글 0\n\n진짜 본문 내용입니다."
        out = _strip_board_meta(src)
        for junk in ("작성자", "작성일", "조회수", "댓글"):
            self.assertNotIn(junk, out)
        self.assertIn("# 6월 진로 특강", out)
        self.assertIn("진짜 본문 내용입니다.", out)

    def test_strips_multiline_metadata(self) -> None:
        # 라벨/값이 줄로 분리된 형식(작성자⏎김**)도 제거한다.
        src = "# 제목\n작성자\n김**\n작성일\n2026-05-28\n조회수\n38\n댓글\n0\n\n진짜 본문"
        out = _strip_board_meta(src)
        for junk in ("작성자", "김**", "조회수", "38", "댓글"):
            self.assertNotIn(junk, out)
        self.assertIn("# 제목", out)
        self.assertIn("진짜 본문", out)

    def test_keeps_sentence_starting_with_label_word(self) -> None:
        # '작성자의 의견은…' 같은 실제 문장은 지우지 않는다(라벨 뒤 구분자 없음).
        src = "작성자의 의견을 존중하여 진행합니다."
        self.assertEqual(_strip_board_meta(src), src)

    def test_strips_bulleted_metadata(self) -> None:
        # 목록형 메타('- 이름: 박**', '- 등록일: …')도 앞 불릿을 떼고 제거한다.
        src = "# 다문화가정 안내\n\n- 이름: 박**\n- 등록일: 2026-05-29 15:47:01"
        out = _strip_board_meta(src)
        for junk in ("이름", "박**", "등록일", "2026-05-29"):
            self.assertNotIn(junk, out)
        self.assertIn("# 다문화가정 안내", out)

    def test_keeps_bulleted_real_list_item(self) -> None:
        # 라벨이 아닌 일반 목록 항목은 보존한다.
        src = "- 신청 방법: 온라인 제출\n- 준비물: 신분증"
        out = _strip_board_meta(src)
        self.assertIn("신청 방법", out)
        self.assertIn("준비물", out)


class SectionHeadingTests(unittest.TestCase):
    def test_marker_line_promoted_to_heading(self) -> None:
        out = _promote_section_headings("◉ 질병결석\n내용 줄")
        self.assertIn("### ◉ 질병결석", out)
        self.assertIn("내용 줄", out)

    def test_sentence_with_marker_not_promoted(self) -> None:
        # 종결어미로 끝나는 '문장'은 제목으로 올리지 않는다.
        out = _promote_section_headings("◉ 아래 내용을 확인하세요.")
        self.assertNotIn("###", out)

    def test_table_and_existing_heading_untouched(self) -> None:
        src = "## 이미 제목\n| a | b |\n| --- | --- |\n| 1 | 2 |"
        self.assertEqual(_promote_section_headings(src), src)


_ATOMS = (
    "https://school.edu/a",
    "2026년 4월 15일",
    "13:30",
    "02-123-4567",
    "a@b.edu",
)


class MaskingTests(unittest.TestCase):
    def test_mask_hides_atoms_then_unmask_restores_them_verbatim(self) -> None:
        raw = "링크 https://school.edu/a 마감 2026년 4월 15일 시각 13:30 문의 02-123-4567 메일 a@b.edu"
        masked, store = mask(raw)

        # 원자값(URL/날짜/시각/전화/이메일)은 LLM 에게 보이지 않게 토큰으로 가려진다.
        for atom in _ATOMS:
            self.assertNotIn(atom, masked)

        # 복원하면 원문 그대로 (한 글자도 안 바뀜).
        restored, dropped = unmask(masked, store)
        for atom in _ATOMS:
            self.assertIn(atom, restored)
        self.assertEqual(dropped, [])

    def test_mask_protects_table_blocks(self) -> None:
        raw = "제목\n| 항목 | 값 |\n| --- | --- |\n| 참가비 | 15000원 |\n끝."
        masked, store = mask(raw)
        self.assertNotIn("참가비", masked)        # 표 통째로 토큰화
        restored, _ = unmask(masked, store)
        self.assertIn("| 참가비 | 15000원 |", restored)

    def test_unmask_appends_dropped_tokens_so_nothing_is_lost(self) -> None:
        _, store = mask("문의 02-123-4567 링크 https://x.edu/a")
        # LLM 이 토큰을 통째로 떨군 상황을 가정 -> 끝에 안전 복원되어야 한다.
        restored, dropped = unmask("정리된 본문만 남고 토큰이 사라짐", store)
        self.assertEqual(len(dropped), len(store))
        self.assertIn("02-123-4567", restored)
        self.assertIn("https://x.edu/a", restored)


class DegenerationGuardTests(unittest.TestCase):
    def test_whitespace_bomb_is_degenerate(self) -> None:
        self.assertTrue(degenerate("내용" + " " * 40, "원문"))

    def test_size_aware_expansion(self) -> None:
        big = "가" * 5000
        self.assertTrue(degenerate("나" * 9000, big))     # 큰 문서: 1.6배 엄격
        small = "가" * 100
        self.assertFalse(degenerate("나" * 200, small))    # 작은 문서: 구조 추가로 정상 팽창 허용

    def test_light_clean_strips_known_junk_but_keeps_body(self) -> None:
        md = "# 안내\n![img](x.png)\n- 1 -\n본문 내용입니다."
        cleaned = light_clean(md)
        self.assertIn("본문 내용입니다.", cleaned)
        self.assertNotIn("![img]", cleaned)
        self.assertNotIn("- 1 -", cleaned)


class _EchoBodyGemini:
    """LLM 이 마스킹 토큰을 그대로 둔 채 산문만 정리했다고 가정(토큰 보존 케이스)."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate_text(self, prompt: str, *, model: str | None = None) -> str:
        self.calls += 1
        body = prompt.split("[추출 markdown]", 1)[-1].strip()
        return "# 정리됨\n" + body


class _BombGemini:
    """LLM 이 매번 공백폭탄을 뱉는 degeneration 상황."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate_text(self, prompt: str, *, model: str | None = None) -> str:
        self.calls += 1
        # 내용 '중간'의 공백폭탄(끝이면 _gen 의 strip 으로 사라짐 — 실제 degeneration 은 중간에 발생)
        return "쓰레기 내용" + " " * 60 + "끝부분"


class RefineTests(unittest.TestCase):
    def test_refine_restores_masked_values_from_llm_output(self) -> None:
        raw = "신청 안내. 링크 https://x.edu/apply 마감 2026년 4월 15일 문의 02-123-4567."
        gem = _EchoBodyGemini()

        out, tag, calls = asyncio.run(refine(raw, gemini=gem))

        self.assertEqual(calls, 1)
        self.assertEqual(tag, "ok")
        self.assertIn("https://x.edu/apply", out)   # URL 복원
        self.assertIn("2026년 4월 15일", out)         # 날짜 복원
        self.assertIn("02-123-4567", out)            # 전화 복원

    def test_refine_falls_back_to_light_clean_on_degeneration(self) -> None:
        raw = "정상적인 가정통신문 본문입니다. 충분히 의미있는 한국어 안내 내용이 들어 있습니다."
        gem = _BombGemini()

        out, tag, calls = asyncio.run(refine(raw, gemini=gem))

        self.assertEqual(tag, "FALLBACK")
        self.assertEqual(calls, 2)                   # 1회 + 재시도 1회
        self.assertIn("정상적인 가정통신문", out)      # 폴백은 원문 보존(light_clean(raw))

    def test_refine_empty_input_skips_gemini(self) -> None:
        class _NeverGemini:
            async def generate_text(self, prompt: str, *, model: str | None = None) -> str:
                raise AssertionError("빈 입력이면 LLM 을 호출하면 안 된다")

        out, tag, calls = asyncio.run(refine("   ", gemini=_NeverGemini()))

        self.assertEqual(tag, "empty")
        self.assertEqual(calls, 0)


class SqueezeSpacesTests(unittest.TestCase):
    def test_collapses_internal_space_bomb(self) -> None:
        self.assertEqual(_squeeze_spaces("값1" + " " * 20 + "값2"), "값1 값2")

    def test_preserves_table_lines_verbatim(self) -> None:
        line = "| 가 |          | 나 |"  # 표 줄은 내부 공백이 많아도 원문 그대로 보존
        self.assertEqual(_squeeze_spaces(line), line)

    def test_preserves_leading_indent_for_nested_lists(self) -> None:
        self.assertEqual(_squeeze_spaces("    - 중첩 항목"), "    - 중첩 항목")

    def test_keeps_normal_single_spacing(self) -> None:
        self.assertEqual(_squeeze_spaces("정상 문장 입니다"), "정상 문장 입니다")

    def test_refine_squeezes_residual_bomb_in_accepted_output(self) -> None:
        class _BombBodyGemini:
            def __init__(self) -> None:
                self.calls = 0

            async def generate_text(self, prompt: str, *, model: str | None = None) -> str:
                self.calls += 1
                # 18칸(30 미만이라 degenerate 통과)짜리 내부 공백폭탄 -> 정상 출력이지만 정리돼야 함
                return "# 안내\n중요" + " " * 18 + "내용입니다."

        out, tag, calls = asyncio.run(refine("정상 본문 충분히 의미있는 내용입니다.", gemini=_BombBodyGemini()))

        self.assertEqual(tag, "ok")
        self.assertNotRegex(out, r" {3,}")        # 3칸+ 연속 공백이 남지 않는다
        self.assertIn("중요 내용입니다.", out)      # 폭탄이 무손실로 줄어든다


if __name__ == "__main__":
    unittest.main()
