# Held-out detail — n03-parent-edu-program (iter-004)

> EVALUATOR-PRIVATE. Not for engineer. Held-out leakage guard: snippets here MUST NOT appear in feedback-report.md or scores.json rationale shared with the engineer (only aggregate trend allowed there).

**Kind:** event-recruitment (parent education program, 3 courses).
**Status this run:** en=admin_review, ru=admin_review, ar=admin_review (all 3 langs admin this iteration).
**iter-003 status:** en=admin_review, ru=ready_to_save, ar=admin_review. -> **ru regressed ready->admin in status only.**

## Per-language axis scores (held identical to iter-003)

| axis | en | ru | ar |
|---|---|---|---|
| fact | 4 | 4 | 4 |
| action | 4 | 4 | 4 |
| tone | 4 | 5 | 5 |
| completeness | 5 | 5 | 5 |
| naturalness | 5 | 5 | 4 |
| culture | 4 | 4 | 4 |
| safety | 5 | 5 | 5 |
| weighted_avg | 4.493 | 4.606 | 4.507 |

## status-regression diagnosis (ru ready->admin)

- **Root:** hard_fact validator FAIL on `fees`. source_value="free", translated_value="расходы на материалы оплачиваются слушателем." — the validator compares the two halves of the SAME source clause "수강료: 무료 (단, 재료비는 학습자 부담)" against each other (one side extracted as "free", the other as "material costs"), producing a false "new critical value" flag.
- **Body is correct.** RU final_translation: "▶ Стоимость курса: Бесплатно. Расходы на материалы оплачиваются слушателем." — this faithfully renders both "무료" (Бесплатно) AND the parenthetical "단, 재료비는 학습자 부담" (расходы на материалы оплачиваются слушателем). No fact added, no fact lost.
- **This is the exact same split-clause false-positive family that hit n03 en and n03 ar in iter-003.** In iter-003 it surfaced in en/ar; this run the LLM hard-fact extractor also split it the same way in ru. Pure run-to-run extraction variance. NOT a quality regression and NOT caused by RU_TARGET_RULES (the rules touch translation register, not fee extraction).
- en/ar same family this run: en translated_value="material costs are to be borne by the learner"; ar translated_value="تكاليف المواد". Bodies: en "Course Fee: Free (However, material costs are to be borne by the learner)"; ar "رسوم الدورة: مجانية. (ملاحظة: يتحمل المتعلم تكاليف المواد)" — both correct.

## RU quality (ru.md checklist) — maintained/improved

- Opening: "Уважаемые родители!" not present here because source has no parent salutation at top; ru opens with the org/title line then program block — appropriate, no fabricated greeting.
- Capitalized Вы: "вместе с Вашими детьми" present.
- Korean concept handling: "주춧돌학교" -> "Краеугольная школа" (meaning translation), "누리집" -> "веб-сайт", "선착순" -> "в порядке живой очереди". Good.
- Dates: "9 июня 2026 г. (вторник) 19:00–21:00" Russian format + 24h. Good.
- «» for program names. Good.

## Comprehension Pass (3 questions)
- 무엇: enroll in one of 3 parent-education courses. CLEAR (all langs).
- 언제: programs within June (each dated 6/9 Tue, 6/11 Thu, 6/27 Sat); apply now until registration closes. CLEAR.
- 어떻게: online first-come via center website (membership signup required first), link https://buly.kr/7x8GXFZ. CLEAR.
- **PASS all 3 langs.**

## Regression watch note for next iter
- Watch the fees split-clause family: it now intermittently trips any of the 3 langs (en/ar in iter-003, +ru in iter-004). Body correct each time. Non-translation (validator) issue.
