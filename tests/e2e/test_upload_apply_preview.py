"""Playwright smoke scaffolding for the upload → apply → preview UI workflow."""

import pytest


@pytest.mark.smoke
@pytest.mark.playwright_smoke
@pytest.mark.skip(reason="UI smoke path requires running frontend and selectors")
def test_upload_apply_preview_flow(page):
    """Exercise the primary upload/apply/preview user journey once selectors are stable."""
    # Example implementation outline (fill in once the UI is wired up):
    # page.goto(f"{base_url}/ui")
    # page.get_by_role("button", name="Upload").click()
    # with page.expect_file_chooser() as chooser:
    #     pass  # chooser.value.set_files("tests/fixtures/sample.pdf")
    # page.get_by_role("button", name="Apply").click()
    # page.get_by_role("button", name="Preview").click()
    # page.wait_for_timeout(1000)  # Replace with explicit assertion on preview contents
    # assert "Return preview" in page.locator("h1").inner_text()
    raise RuntimeError("This test should remain skipped until the UI flow is automated")
