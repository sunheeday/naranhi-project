# Held-out detail — n04-college-info-session (iter-004)

> EVALUATOR-PRIVATE. Not for engineer. Held-out leakage guard: snippets here MUST NOT appear in feedback-report.md or scores.json rationale shared with the engineer (only aggregate trend allowed there).

**Kind:** event-info-session (career/college admissions session, 2 speakers).
**Status this run:** en=admin_review, ru=admin_review, ar=ready_to_save.
**iter-003 status:** en=ready_to_save, ru=admin_review, ar=ready_to_save. -> **en regressed ready->admin in status only.**

## Per-language axis scores (held identical to iter-003)

| axis | en | ru | ar |
|---|---|---|---|
| fact | 5 | 5 | 5 |
| action | 5 | 5 | 5 |
| tone | 4 | 5 | 5 |
| completeness | 5 | 5 | 5 |
| naturalness | 5 | 5 | 4 |
| culture | 4 | 4 | 4 |
| safety | 5 | 5 | 5 |
| weighted_avg | 4.775 | 4.887 | 4.789 |

## status-regression diagnosis (en ready->admin)

- **Root:** hard_fact validator FAIL on `grade_class_targets`. source_value="grade:1, grade:2, grade:3", translated_value="" (empty). The target-side extractor returned an empty grade set, so the validator flags the source grades as "missing".
- **Body is correct.** EN final_translation: "b. Target Audience: Students in grades 1, 2, and 3 of our school, and their parents (guardians)". All three grades present and correct.
- **This is the exact same empty-extraction false-positive family that hit n04 ru in iter-003.** In iter-003 it surfaced in ru (and en had recovered to ready via CS#1); this run the LLM target-fact extractor returned empty grades for en instead. Pure run-to-run extraction variance. NOT a quality regression and NOT caused by RU_TARGET_RULES (en prompt unchanged; this is the en pipeline's target extraction).
- ru same family this run (continuation from iter-003): source "grade:1,2,3" vs translated "" empty. Body: "Учащиеся 1-го, 2-го и 3-го классов нашей школы и их родители (опекуны)" — correct.
- ar recovered/stayed ready (hard_fact passed, attempts=1).

## RU quality (ru.md checklist) — maintained/improved vs iter-003

- Opening: iter-003 "Уважаемые родители." -> iter-004 "Уважаемые родители!" + "Приветствуем Вас." — matches ru.md preferred salutation form.
- Request: iter-004 "Просим Вас проявить большой интерес и принять участие" (ru.md 'Просим Вас' pattern); iter-003 used "Мы убедительно просим учащихся и родителей принять участие".
- Capitalized Вы maintained ("если вы уверены" — note one lowercase в в final caution line "если вы уверены в своем участии"; minor, consistent with iter-003 which had the same; does not lift/lower the already-5.0 tone).
- Dates: "9 июня 2026 г. (вторник) 15:00–17:00" Russian format + 24h. "20:00" 24h. Good.
- Numeral-noun: "Учащиеся 1-го, 2-го и 3-го классов" correct ordinal agreement.
- Speaker names transliterated: "Ким Ха Ун", "Чхве Чон Бом". Good. (iter-003 used hyphenated "Ким Ха-ун" — cosmetic, both fine.)

## Comprehension Pass (3 questions)
- 무엇: register to attend the career/admissions info session. CLEAR (all langs).
- 언제: session 6/9 (Tue) 15:00-17:00; apply 5/26-6/3 (Wed) 20:00. CLEAR.
- 어떻게: online survey link https://m.site.naver.com/28Aoi. CLEAR.
- **PASS all 3 langs.**

## Regression watch note for next iter
- grade_class_targets empty-target-extraction family rotates across langs run-to-run (en ready in iter-003 -> admin in iter-004; ru admin both runs; n06 also affected). Body correct each time. Non-translation (validator/extraction) issue, independent of RU_TARGET_RULES.
