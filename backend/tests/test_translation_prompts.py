import unittest

from app.translation.prompts import (
    build_supabase_payload_prompt,
    extract_source_hard_facts_prompt,
    extract_target_hard_facts_prompt,
)


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

    def test_source_hard_fact_prompt_strengthens_action_required_task_examples(self):
        prompt = extract_source_hard_facts_prompt("도시락과 물을 준비해 주세요. 참가 신청서를 제출해 주세요.")

        self.assertIn("actions_required` should capture what the parent/student must do as short task phrases", prompt)
        self.assertIn("도시락과 물 준비", prompt)
        self.assertIn("submit/return/apply/register/pay/confirm/reply", prompt)
        self.assertIn("If `actions_required` contains only bare nouns like `신청서`", prompt)

    def test_hard_fact_prompts_include_migrant_parent_north_star_and_workflow(self):
        source_prompt = extract_source_hard_facts_prompt("체험학습 안내")
        target_prompt = extract_target_hard_facts_prompt(
            target_language="en",
            target_translation="Field trip notice",
        )

        for prompt in (source_prompt, target_prompt):
            self.assertIn("migrant parent", prompt)
            self.assertIn("WHAT must happen, WHEN it happens or is due, and HOW they must respond", prompt)
            self.assertIn("Read the notice line by line and section by section", prompt)
            self.assertIn("posting/admin/meta/header/footer/signature timestamp", prompt)
            self.assertIn("Working ledger before JSON", prompt)
            self.assertIn("First separate the notice into: admin/meta, event schedule", prompt)

    def test_target_hard_fact_prompt_preserves_parent_action_usability(self):
        prompt = extract_target_hard_facts_prompt(
            target_language="en",
            target_translation="Please submit the form by June 1 to the homeroom teacher.",
        )

        self.assertIn("Preserve parent-action usability", prompt)
        self.assertIn("Final self-check: a migrant parent reading only TARGET_TRANSLATION", prompt)
        self.assertIn("recover each concrete fact separately", prompt)
        self.assertIn("Submit the consent form", prompt)
        self.assertIn("please submit", prompt)

    def test_build_supabase_payload_prompt_marks_action_section_as_canonical_card_input(self):
        prompt = build_supabase_payload_prompt(
            source_text="참가 신청서를 제출해 주세요.",
            final_target_translation="Please submit the participation form.",
            source_hard_facts={"hard_facts": {"actions_required": [{"raw_text": "참가 신청서 제출"}]}},
            validation_results={"verdict": "PASS"},
            target_language="en",
        )

        self.assertIn("actions_required is the primary canonical card input", prompt)
        self.assertIn("card_sections_ko.action", prompt)
        self.assertIn("legacy compatibility sections", prompt)
        self.assertIn("Do not rely on them to carry the only actionable instruction.", prompt)


if __name__ == "__main__":
    unittest.main()
