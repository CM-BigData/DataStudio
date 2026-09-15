# Question Augmentation Real Question Samples

These samples are a compact, reproducible validation subset for `question_augmentation_synthesis`.

## Sources and selection

- `squad_qa_001` and `squad_qa_002`: Selected from public SQuAD v1.1 example-style reading-comprehension questions. They cover factoid QA questions with different lengths.
- `search_googletrends_001`: A common passport-renewal search query pattern inspired by Google Trends search-query usage. It covers short keyword-style search input.
- `search_stackoverflow_001`: A common Python CSV search-query pattern inspired by Stack Overflow tagged-question discovery. It covers technical search input.
- `education_khan_001`: A Khan Academy-style arithmetic word problem. It covers English education questions with numeric constraints.
- `education_cn_exam_001`: A common PEP textbook-style Chinese fraction word problem. It covers Chinese education questions.
- `customer_support_001`: A common account-recovery FAQ pattern inspired by Google Account Help. It covers English customer-support questions.
- `customer_support_002`: A common ecommerce after-sales FAQ pattern inspired by Taobao Help. It covers Chinese customer-support questions.

## Use reason

The subset intentionally stays at 8 records so local validation can run quickly while covering QA, search-style questions, education questions, and customer-support questions. The expected behavior is question augmentation: paraphrases, search-query variants, and context-enriched variants. It is not question decomposition into reasoning sub-questions.
