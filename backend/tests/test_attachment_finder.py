from __future__ import annotations

import unittest

from extractor.attachment_finder import find_attachments


class AttachmentFinderTests(unittest.TestCase):
    def test_finds_sen_server_file_objects(self) -> None:
        html = """
        <script>
          var serverFileObjArray = new Array();
          var serverFileObj = new Object();
          serverFileObj["name"] = "2026학년도 현장체험학습 안내.hwp";
          serverFileObj["size"] = "2237952";
          serverFileObj["atchFileId"] = "FILE_000000012279972";
          serverFileObj["fileSn"] = "0";
          serverFileObjArray.push(serverFileObj);
          function fn_egov_downFile(atchFileId, fileSn){
            window.open("/dggb/board/boardFile/downFile.do;jsessionid=abc?atchFileId="+atchFileId+"&fileSn="+fileSn+"");
          }
        </script>
        """

        refs = find_attachments("https://yeongdeungpo.sen.ms.kr/dggb/module/board/selectBoardDetailAjax.do", html)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].filename, "2026학년도 현장체험학습 안내.hwp")
        self.assertIn("/dggb/board/boardFile/downFile.do", refs[0].url)
        self.assertIn("atchFileId=FILE_000000012279972", refs[0].url)
        self.assertIn("fileSn=0", refs[0].url)

    def test_finds_literal_download_function_call(self) -> None:
        html = """<a href="#" onclick="fn_egov_downFile('FILE_123', '2')">다운로드</a>"""

        refs = find_attachments("https://example.school/detail", html)

        self.assertEqual(len(refs), 1)
        self.assertIn("atchFileId=FILE_123", refs[0].url)
        self.assertIn("fileSn=2", refs[0].url)

    def test_ignores_common_school_homepage_guideline_file(self) -> None:
        html = """
        <a href="/boardCnts/fileDown.do?fileSeq=real">가정통신문.hwp</a>
        <a href="/UserFiles/call/학교통합홈페이지+운영지침.hwp">학교통합홈페이지 운영지침</a>
        """

        refs = find_attachments("https://example.school/detail", html)

        self.assertEqual([ref.filename for ref in refs], ["가정통신문.hwp"])

    def test_ignores_url_file_management_downloads(self) -> None:
        html = """
        <a href="/boardCnts/fileDown.do?fileSeq=real">가정통신문.hwp</a>
        <a href="/apple/urlfileMgt/filedown.do?fileSeq=common">다운로드</a>
        """

        refs = find_attachments("https://example.school/detail", html)

        self.assertEqual([ref.filename for ref in refs], ["가정통신문.hwp"])

    def test_dedupes_repeated_meaningful_filenames(self) -> None:
        html = """
        <a href="/boardCnts/fileDown.do?fileSeq=one">도서관 안내장.hwp</a>
        <a href="/boardCnts/fileDown.do?fileSeq=two">도서관 안내장.hwp</a>
        """

        refs = find_attachments("https://example.school/detail", html)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].filename, "도서관 안내장.hwp")


if __name__ == "__main__":
    unittest.main()
