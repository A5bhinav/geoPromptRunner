from __future__ import annotations

from typing import Any

from src.audit.checks.schema import (
    SchemaClass,
    check_schema,
    flatten_typed_nodes,
)
from src.audit.crawl.models import FetchMeta, PageCategory, PageRecord


def _page(
    json_ld: list[dict[str, Any]],
    visible_text: str = "",
    *,
    blocked: bool = False,
    category: PageCategory = PageCategory.OTHER,
) -> PageRecord:
    return PageRecord(
        url="https://x.com/",
        normalized_url="https://x.com/",
        category=category,
        fetch_meta=FetchMeta(
            status_code=200,
            final_url="https://x.com/",
            fetched_at="t",
            was_rendered=False,
            request_ua="ua",
            blocked=blocked,
            headers={},
        ),
        content_sha256="x",
        extracted_text=visible_text,
        json_ld=json_ld,
    )


_VALID_PRODUCT = {
    "@type": "Product",
    "name": "Acme Widget",
    "image": "https://x.com/w.png",
    "brand": {"@type": "Brand", "name": "Acme"},
    "offers": {
        "@type": "Offer",
        "price": "29.99",
        "priceCurrency": "USD",
        "availability": "https://schema.org/InStock",
    },
    "aggregateRating": {
        "@type": "AggregateRating",
        "ratingValue": "4.5",
        "reviewCount": "210",
    },
}


def test_no_schema_fails() -> None:
    assert check_schema(_page([])).classification is SchemaClass.FAIL


def test_blocked_is_ungradeable() -> None:
    assert check_schema(_page([], blocked=True)).classification is SchemaClass.UNGRADEABLE


def test_valid_product_passes() -> None:
    visible = "Acme Widget — only 29.99 USD. Rated 4.5 stars by 210 buyers."
    result = check_schema(_page([_VALID_PRODUCT], visible))
    assert result.classification is SchemaClass.PASS
    assert "Product" in result.types_found
    assert "Offer" in result.types_found
    assert "AggregateRating" in result.types_found
    assert result.mismatches == []


def test_product_missing_required_is_partial() -> None:
    # No name, and none of offers/review/aggregateRating -> required + one_of fail.
    result = check_schema(_page([{"@type": "Product", "description": "a thing"}], "a thing"))
    assert result.classification is SchemaClass.PARTIAL
    product = next(f for f in result.findings if f.type_name == "Product")
    assert "name" in product.missing_required
    assert product.missing_one_of  # offers/review/aggregateRating group unmet


def test_fabricated_rating_flagged() -> None:
    # Schema claims 4.9 but the visible text never shows it -> content mismatch.
    node = {
        "@type": "Product",
        "name": "Acme Widget",
        "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.9", "reviewCount": "3"},
    }
    result = check_schema(_page([node], "Acme Widget is a great product."))
    assert result.classification is SchemaClass.PARTIAL
    assert any(m.field_name == "ratingValue" for m in result.mismatches)


def test_graph_and_type_list_flattening() -> None:
    blocks = [
        {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "Organization", "name": "Acme", "url": "https://x.com"},
                {"@type": ["WebSite", "CreativeWork"], "name": "Acme", "url": "https://x.com"},
            ],
        }
    ]
    nodes = flatten_typed_nodes(blocks)
    assert len(nodes) == 2
    result = check_schema(_page(blocks, "Acme"))
    assert "Organization" in result.types_found
    assert "WebSite" in result.types_found
    assert result.evidence["organization_present"] is True


def test_recommended_gaps_surface_without_failing() -> None:
    # Organization with only the required name -> PASS, but recommended gaps noted.
    result = check_schema(_page([{"@type": "Organization", "name": "Acme"}], "Acme"))
    assert result.classification is SchemaClass.PASS
    assert "logo" in result.evidence["recommended_gaps"]


def test_missing_expected_type_is_partial() -> None:
    # A pricing page with only Organization schema should expose Product/Offer.
    result = check_schema(
        _page([{"@type": "Organization", "name": "Acme"}], "Acme", category=PageCategory.PRICING)
    )
    assert result.classification is SchemaClass.PARTIAL
    assert set(result.evidence["missing_expected_types"]) == {"Product", "Offer"}


def test_sameas_links_extracted_and_classified() -> None:
    org = {
        "@type": "Organization",
        "name": "Acme",
        "sameAs": ["https://twitter.com/acme", "https://www.linkedin.com/company/acme"],
    }
    result = check_schema(_page([org], "Acme"))
    same_as = result.evidence["same_as"]
    assert same_as["count"] == 2
    assert set(same_as["platforms"]) == {"twitter.com", "linkedin.com"}
