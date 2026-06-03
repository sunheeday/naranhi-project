from __future__ import annotations

import unittest

from extractor.attachment_finder import find_attachments
from extractor.html_text_extractor import extract_html_text
from extractor.models import SourceExtraction
from extractor.notice_structurer import combined_raw_text
from extractor.quality import text_fingerprint
from extractor.source_merger import assign_roles_and_dedupe


class NoticeTextCleanupTests(unittest.TestCase):
    def test_combined_raw_text_omits_debug_labels(self) -> None:
        text = combined_raw_text(
            [
                SourceExtraction(
                    source_id="html_body_1",
                    source_type="html_body",
                    source_role="primary",
                    origin_url="https://example.edu",
                    filename="",
                    file_hash="",
                    text_fingerprint="fp-1",
                    duplicate_of=None,
                    extraction_method="html",
                    status="success",
                    raw_text="본문입니다",
                )
            ],
            ["html_body_1"],
        )

        self.assertEqual(text, "본문입니다")
        self.assertNotIn("[html_body_1 html_body]", text)

    def test_combined_raw_text_skips_short_html_metadata_when_attachment_exists(self) -> None:
        text = combined_raw_text(
            [
                SourceExtraction(
                    source_id="attachment_hwp_1",
                    source_type="attachment_hwp",
                    source_role="primary",
                    origin_url="https://example.edu/file.hwp",
                    filename="file.hwp",
                    file_hash="",
                    text_fingerprint="fp-1",
                    duplicate_of=None,
                    extraction_method="hwp",
                    status="success",
                    raw_text="실제 첨부 본문입니다.",
                ),
                SourceExtraction(
                    source_id="html_body_1",
                    source_type="html_body",
                    source_role="primary",
                    origin_url="https://example.edu",
                    filename="",
                    file_hash="",
                    text_fingerprint="fp-2",
                    duplicate_of=None,
                    extraction_method="html",
                    status="success",
                    raw_text="공지 제목\n작성자\n홍길동\n등록일\n2026.05.20\n조회수\n51",
                ),
            ],
            ["attachment_hwp_1", "html_body_1"],
        )

        self.assertEqual(text, "실제 첨부 본문입니다.")

    def test_extract_html_text_drops_attachment_ui_lines(self) -> None:
        html = """
        <div class="board_view">
          <p>가정통신문 본문</p>
          <p>첨부파일</p>
          <p>첨부파일 미리보기</p>
          <p>미리보기</p>
          <p>바로듣기</p>
        </div>
        """

        text = extract_html_text(html)

        self.assertIn("가정통신문 본문", text)
        self.assertNotIn("첨부파일 미리보기", text)
        self.assertNotIn("바로듣기", text)

    def test_find_attachments_reads_dext5_single_quoted_uploads(self) -> None:
        html = """
        <script>
        DEXT5UPLOAD.AddUploadedFile(
          'ae1794',
          '안내문.hwp',
          '/upload/school/notice.hwp',
          '86528',
          'ae1794',
          G_UploadID
        );
        </script>
        """

        refs = find_attachments("https://school.example.edu/notice", html)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].filename, "안내문.hwp")
        self.assertEqual(refs[0].url, "https://school.example.edu/upload/school/notice.hwp")


def _source(source_id: str, source_type: str, raw_text: str) -> SourceExtraction:
    return SourceExtraction(
        source_id=source_id,
        source_type=source_type,
        source_role="",
        origin_url="",
        filename="",
        file_hash="",
        text_fingerprint=text_fingerprint(raw_text),
        duplicate_of=None,
        extraction_method="test",
        status="success",
        raw_text=raw_text,
    )


# 40단어 이상인 본문(상담주간 안내). 첨부 HWP 는 이 본문 + 추가 섹션(상위집합).
_BODY = (
    "2026학년도 1학기 학부모 상담주간 운영 안내입니다. 우리 학교는 학생들의 건강한 성장과 "
    "학교생활 적응을 돕기 위하여 담임교사와 학부모님 간의 상담주간을 운영합니다. 상담 기간은 "
    "다음주 월요일부터 금요일까지이며 상담 시간은 오후 두시부터 네시까지입니다. 희망하시는 "
    "학부모님께서는 사전에 담임선생님께 연락하시어 일정을 예약해 주시기 바랍니다. 자녀의 건강한 "
    "학교생활을 위해 많은 관심과 참여 부탁드립니다."
)
_HWP_SUPERSET = _BODY + (
    "\n\n[상담 신청 방법]\n1. 알림장으로 신청서를 작성합니다.\n2. 학교 홈페이지 게시판에 신청합니다.\n"
    "3. 담임교사 휴대전화로 문자를 보냅니다.\n[준비사항] 자녀의 교우관계와 학습태도 관련 궁금한 점을 "
    "미리 정리해 오시면 알찬 상담이 됩니다. 작성자 교무부장."
)


class DuplicateContainmentTests(unittest.TestCase):
    """본문 ⊂ 첨부(HWP) 상위집합 중복 제거 + 손실/오판 방지 안전장치."""

    def _roles(self, sources: list[SourceExtraction]) -> tuple[dict[str, str], list[str]]:
        merged, included = assign_roles_and_dedupe(sources)
        return {source.source_id: source.source_role for source in merged}, included

    def test_body_contained_in_attachment_is_deduped(self) -> None:
        roles, included = self._roles([
            _source("body", "html_body", _BODY),
            _source("hwp", "attachment_hwp", _HWP_SUPERSET),
        ])
        # 본문이 첨부에 통째로 들어있으면 첨부만 남긴다(본문 중복 제거).
        self.assertEqual(roles["body"], "duplicate")
        self.assertEqual(roles["hwp"], "primary")
        self.assertEqual(included, ["hwp"])

    def test_body_only_deadline_is_preserved(self) -> None:
        body = _BODY + " 상담 신청 마감은 3월 30일까지입니다."  # '30' 은 첨부에 없음
        roles, included = self._roles([
            _source("body", "html_body", body),
            _source("hwp", "attachment_hwp", _HWP_SUPERSET),
        ])
        # 본문에만 있는 마감일이 사라지면 안 되므로 둘 다 유지.
        self.assertEqual(roles["body"], "primary")
        self.assertEqual(roles["hwp"], "primary")
        self.assertCountEqual(included, ["hwp", "body"])

    def test_short_pointer_body_is_not_deduped(self) -> None:
        roles, included = self._roles([
            _source("body", "html_body", "자세한 내용은 첨부파일을 확인해 주시기 바랍니다."),
            _source("hwp", "attachment_hwp", _HWP_SUPERSET),
        ])
        # 40단어 미만 짧은 안내문은 오판 방지를 위해 합치지 않는다.
        self.assertEqual(roles["body"], "primary")
        self.assertEqual(roles["hwp"], "primary")
        self.assertCountEqual(included, ["hwp", "body"])

    def test_different_notices_are_not_merged(self) -> None:
        first = (
            "2026학년도 봄 현장체험학습 안내. 4학년 학생들이 경주 역사 유적지로 현장체험학습을 "
            "떠납니다. 출발 시간과 준비물 도시락 우비를 확인 바랍니다. 안전하게 다녀오겠습니다."
        )
        second = (
            "2026학년도 독서 골든벨 대회 개최 안내. 전교생 대상으로 독서 골든벨 대회를 개최합니다. "
            "지정 도서를 읽고 문제를 풀어 우승자를 가립니다. 도서관에서 진행합니다."
        )
        roles, included = self._roles([
            _source("first", "html_body", first),
            _source("second", "attachment_hwp", second),
        ])
        self.assertEqual(roles["first"], "primary")
        self.assertEqual(roles["second"], "primary")
        self.assertCountEqual(included, ["first", "second"])

    def test_longer_source_kept_even_if_lower_priority(self) -> None:
        # 더 긴 쪽이 본문(우선순위 낮음)이고 더 짧은 부분집합이 첨부 HWP(우선순위 높음)여도,
        # 내용이 더 많은(상위집합) 쪽을 남겨야 한다 — _best_source 보정 검증.
        roles, included = self._roles([
            _source("longbody", "html_body", _HWP_SUPERSET),  # 더 긴 본문(70)
            _source("shorthwp", "attachment_hwp", _BODY),     # 더 짧은 부분집합(90)
        ])
        self.assertEqual(roles["longbody"], "primary")
        self.assertEqual(roles["shorthwp"], "duplicate")
        self.assertEqual(included, ["longbody"])


if __name__ == "__main__":
    unittest.main()
