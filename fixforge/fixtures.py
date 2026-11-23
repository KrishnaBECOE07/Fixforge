"""Curated, deterministic cases. These are demonstrations, never AI claims."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fixture:
    id: str
    repo: str
    number: int
    title: str
    body: str
    tags: tuple[str, ...]
    path: str
    original: str
    replacement: str
    existing_test: str
    regression: str
    rationale: str

    def public(self) -> dict:
        return {k: getattr(self, k) for k in ("id", "repo", "number", "title", "body", "tags")}


FIXTURES = {
    f.id: f for f in [
        Fixture(
            "payment-zero", "acme / payment-service", 142,
            "Payment API crashes when the amount is zero",
            "A zero-value invoice should have a fee rate of 0. Instead, fee_rate(0, 0) raises "
            "ZeroDivisionError. Preserve nonzero calculations and continue rejecting negative amounts.",
            ("bug", "payments", "edge case"), "payments.py",
            'def fee_rate(amount: float, fee: float) -> float:\n'
            '    """Return a payment fee as a fraction of the invoice amount."""\n'
            '    if amount < 0:\n        raise ValueError("Amount cannot be negative")\n'
            '    return fee / amount\n',
            'def fee_rate(amount: float, fee: float) -> float:\n'
            '    """Return a payment fee as a fraction of the invoice amount."""\n'
            '    if amount < 0:\n        raise ValueError("Amount cannot be negative")\n'
            '    if amount == 0:\n        return 0.0\n    return fee / amount\n',
            'import unittest\nfrom payments import fee_rate\n\nclass PaymentsTest(unittest.TestCase):\n'
            '    def test_normal_fee(self):\n        self.assertEqual(fee_rate(100, 3), 0.03)\n'
            '    def test_negative_amount(self):\n        with self.assertRaises(ValueError):\n            fee_rate(-1, 0)\n',
            'import unittest\nfrom payments import fee_rate\n\nclass ZeroPaymentTest(unittest.TestCase):\n'
            '    def test_zero_invoice(self):\n        self.assertEqual(fee_rate(0, 0), 0.0)\n'
            '    def test_zero_amount_with_fee(self):\n        self.assertEqual(fee_rate(0, 2), 0.0)\n',
            "The division assumes a positive invoice. A guard after negative-amount validation "
            "implements the issue's zero-value contract while preserving existing calculations.",
        ),
        Fixture(
            "pagination-empty", "acme / catalog-api", 87,
            "Empty collections report a negative last page",
            "last_page(0, 20) returns -1. The API uses zero-indexed pages and requires an empty "
            "collection to return 0. Exact page boundaries must remain correct.",
            ("bug", "pagination", "boundary"), "pagination.py",
            'def last_page(total: int, page_size: int) -> int:\n'
            '    """Return the zero-indexed final page of a collection."""\n'
            '    if total < 0 or page_size <= 0:\n        raise ValueError("Invalid pagination inputs")\n'
            '    return (total - 1) // page_size\n',
            'def last_page(total: int, page_size: int) -> int:\n'
            '    """Return the zero-indexed final page of a collection."""\n'
            '    if total < 0 or page_size <= 0:\n        raise ValueError("Invalid pagination inputs")\n'
            '    return max(0, (total - 1) // page_size)\n',
            'import unittest\nfrom pagination import last_page\n\nclass PagesTest(unittest.TestCase):\n'
            '    def test_full_page(self):\n        self.assertEqual(last_page(20, 20), 0)\n'
            '    def test_next_page(self):\n        self.assertEqual(last_page(21, 20), 1)\n'
            '    def test_invalid_size(self):\n        with self.assertRaises(ValueError):\n            last_page(1, 0)\n',
            'import unittest\nfrom pagination import last_page\n\nclass EmptyPagesTest(unittest.TestCase):\n'
            '    def test_empty_collection(self):\n        self.assertEqual(last_page(0, 20), 0)\n'
            '    def test_single_item(self):\n        self.assertEqual(last_page(1, 20), 0)\n',
            "Python floor division makes the empty-case numerator negative. Clamping the result "
            "to zero preserves page boundaries and input validation.",
        ),
        Fixture(
            "slug-whitespace", "acme / content-engine", 63,
            "Article slugs keep leading and trailing hyphens",
            "slugify('  Hello World  ') should return 'hello-world'. Repeated whitespace should "
            "collapse to one separator, and a whitespace-only title should become an empty string.",
            ("bug", "text processing", "normalization"), "slugs.py",
            'def slugify(title: str) -> str:\n'
            '    """Normalize a title into a lowercase, whitespace-separated slug."""\n'
            '    return title.lower().replace(" ", "-")\n',
            'def slugify(title: str) -> str:\n'
            '    """Normalize a title into a lowercase, whitespace-separated slug."""\n'
            '    return "-".join(title.lower().split())\n',
            'import unittest\nfrom slugs import slugify\n\nclass SlugsTest(unittest.TestCase):\n'
            '    def test_basic_title(self):\n        self.assertEqual(slugify("Hello World"), "hello-world")\n'
            '    def test_empty_title(self):\n        self.assertEqual(slugify(""), "")\n',
            'import unittest\nfrom slugs import slugify\n\nclass WhitespaceSlugTest(unittest.TestCase):\n'
            '    def test_outer_spaces(self):\n        self.assertEqual(slugify("  Hello World  "), "hello-world")\n'
            '    def test_mixed_whitespace(self):\n        self.assertEqual(slugify("Hello\\t  World"), "hello-world")\n'
            '    def test_whitespace_only(self):\n        self.assertEqual(slugify("   "), "")\n',
            "Replacing individual spaces leaves empty tokens and misses tabs. Splitting on "
            "whitespace and joining once handles both cases without adding dependencies.",
        ),
    ]
}
