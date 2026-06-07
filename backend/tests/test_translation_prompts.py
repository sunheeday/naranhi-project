import unittest

from app.translation.prompts import extract_source_hard_facts_prompt


class TranslationPromptsTest(unittest.TestCase):
    def test_source_hard_fact_prompt_excludes_admin_dates_from_schedule_dates(self):
        prompt = extract_source_hard_facts_prompt("작성일 2026.05.22\n체험학습일 2026.05.30")

        self.assertIn("Do NOT put board/admin metadata dates", prompt)
        self.assertIn("작성일", prompt)
        self.assertIn("게시일", prompt)
        self.assertIn("dates` must contain only real occurrence", prompt)

    def test_source_hard_fact_prompt_blocks_prohibited_items_from_materials(self):
        prompt = extract_source_hard_facts_prompt("준비물: 도시락\n반입금지: 장난감 칼")

        self.assertIn("Do NOT put prohibited / banned / confiscated / restricted items into `materials`", prompt)
        self.assertIn("금지물품", prompt)
        self.assertIn("반입금지", prompt)
        self.assertIn("warnings", prompt)

    def test_source_hard_fact_prompt_adds_role_confusion_self_check(self):
        prompt = extract_source_hard_facts_prompt("등록일 05.22.\n준비물 또는 금지물품이 애매한 경우")

        self.assertIn("If `dates` only contains posting/admin metadata dates, remove them.", prompt)
        self.assertIn("If an item in `materials` appears in the same phrase as `금지`", prompt)


if __name__ == "__main__":
    unittest.main()
