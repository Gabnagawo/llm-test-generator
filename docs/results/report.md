# Benchmark report

Generated with `uv run ltg report runs/qwen3-8b-think-off` from the attempt log in [benchmark/qwen3-8b-think-off/attempts.json](benchmark/qwen3-8b-think-off/attempts.json).

## Comparison

| model | stories | valid on 1st attempt | after repair 1 | after repair 2 | failed | LLM calls | median LLM latency | wall time |
|---|---|---|---|---|---|---|---|---|
| ollama qwen3:8b (think=off) | 12 | 8/12 (67 %) | 8/12 (67 %) | 8/12 (67 %) | 4 | 20 | 29.2 s | 12.1 min |

## ollama qwen3:8b (think=off) - run `qwen3-8b-think-off`

Mode `run`: a test counts as valid when it passed against the live app. Prompt version `2026-11-12.1`, max repairs 2.

- LLM calls: 20 (provider errors: 0), static rejections: 0, execution failures: 12
- First-attempt failure categories: assertion_failed 3, strict_mode_violation 1
- All failure categories: assertion_failed 8, python_error 3, strict_mode_violation 1

| story | attempts | result | attempt outcomes |
|---|---|---|---|
| successful-login | 1 | passed_first_attempt | pass |
| locked-out-user-is-rejected | 1 | passed_first_attempt | pass |
| wrong-password-is-rejected | 1 | passed_first_attempt | pass |
| logout-from-the-menu | 3 | failed | assertion_failed -> assertion_failed -> assertion_failed |
| adding-a-product-updates-the-cart-badge | 1 | passed_first_attempt | pass |
| removing-a-product-from-the-cart-page-empties-the-cart | 3 | failed | assertion_failed -> assertion_failed -> assertion_failed |
| the-cart-lists-every-product-that-was-added | 3 | failed | assertion_failed -> python_error -> assertion_failed |
| sorting-by-price-from-low-to-high | 1 | passed_first_attempt | pass |
| sorting-by-name-from-z-to-a | 1 | passed_first_attempt | pass |
| opening-a-product-detail-page | 3 | failed | strict_mode_violation -> python_error -> python_error |
| complete-a-purchase | 1 | passed_first_attempt | pass |
| checkout-requires-a-first-name | 1 | passed_first_attempt | pass |
