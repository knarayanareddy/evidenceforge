# Finance/extraction self-assessment (PREPARED FOR independent review — NOT an approval)
Rules implemented+tested: Decimal-only money math, base-unit = raw x scale, locale
grouping (en 1,234.56 / de 1.234,56) tested independently of public examples,
dash/empty never zero, explicit missing_reason (never invented values), exactly 8 fields.
FINDING (from real docling-parse pilot): the bundled PDF's actual text ends at
"Currency EUR"; the "; units 1000" scale statement exists only in the authored fixture
JSON text, not the PDF. Fixture profile therefore reports scale=1000 from authored
metadata while docling_local/1 honestly reports scale=1/revenue 1234 on the same file.
Fixture values must never be cited as parser accuracy. Domain corpus/holdout, dual
annotation and finance signoff: PENDING INDEPENDENT REVIEW.
