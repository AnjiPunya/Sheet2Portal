from app.services.analysis.title import generate_portal_title


def test_strips_extension_and_underscores_and_title_cases():
    assert generate_portal_title("quarterly_report.xlsx") == "Quarterly Report"


def test_strips_hyphens_too():
    assert generate_portal_title("quarterly-report.csv") == "Quarterly Report"


def test_removes_numeric_duplicate_suffix():
    assert generate_portal_title("quarterly_report (1).xlsx") == "Quarterly Report"
    assert generate_portal_title("quarterly_report (12).xlsx") == "Quarterly Report"


def test_removes_copy_suffix():
    assert generate_portal_title("quarterly_report copy.xlsx") == "Quarterly Report"
    assert generate_portal_title("quarterly_report_copy_2.xlsx") == "Quarterly Report"


def test_removes_filler_technical_words():
    # "sample_data" is exactly the kind of noise that should disappear --
    # but only once a real domain/content word remains.
    assert generate_portal_title("vendor_catalog_sample_data_final.xlsx") == "Vendor Catalog"


def test_domain_real_estate_construction():
    # This is the exact filename shape that prompted this feature.
    title = generate_portal_title("real_estate_construction_portal_sample_data (1).xlsx")
    assert title == "Real Estate Construction Management Portal"


def test_domain_inventory():
    assert generate_portal_title("warehouse_inventory_tracker.xlsx") == "Inventory Management Portal"


def test_domain_sales():
    assert generate_portal_title("sales_pipeline_q3.xlsx") == "Sales Management Portal"


def test_unknown_domain_falls_back_to_cleaned_filename_not_invented_domain():
    title = generate_portal_title("Q3_Marketing_Notes_Final (2).xlsx")
    assert title not in (
        "Real Estate Construction Management Portal",
        "Inventory Management Portal",
        "Sales Management Portal",
    )
    assert title == "Q3 Marketing Notes"


def test_ambiguous_domain_tie_falls_back_to_cleaned_filename():
    # Equal evidence for two domains -- not confident enough to pick one.
    title = generate_portal_title("sales_and_inventory_summary.xlsx")
    assert title == "Sales and Inventory Summary"  # connecting words stay lower-case


def test_all_filler_words_does_not_collapse_to_empty():
    assert generate_portal_title("sample_data.xlsx") == "Sample Data"


def test_degenerate_name_falls_back_to_generic_title():
    assert generate_portal_title("(1).xlsx") == "Business Portal"


def test_original_filename_itself_is_never_mutated():
    original = "real_estate_construction_portal_sample_data (1).xlsx"
    generate_portal_title(original)
    assert original == "real_estate_construction_portal_sample_data (1).xlsx"
