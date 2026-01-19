"""
Playwright script to record a demo video of the Inmor Admin UI.
This script follows the steps from create_redis_db_data.py but through the UI.
"""

import time
from playwright.sync_api import sync_playwright, Page

# Test data
TRUST_MARK_TYPES = [
    {
        "tmtype": "https://sunet.se/does_not_exist_trustmark",
        "valid_for": "8760",
        "autorenew": True,
        "renewal_time": "48",
    },
    {
        "tmtype": "https://example.com/trust_mark_type",
        "valid_for": "720",
        "autorenew": True,
        "renewal_time": "48",
    },
]

# TrustMarks to create (domain, tmt_index 1-based)
TRUST_MARKS = [
    ("https://fakerp0.labb.sunet.se", 1),
    ("https://fakeop0.labb.sunet.se", 1),
    ("https://fakerp1.labb.sunet.se", 1),
    ("https://localhost:8080", 1),
    # Extra trustmarks for RPs with tmt 2
    ("https://fakerp0.labb.sunet.se", 2),
    ("https://fakerp1.labb.sunet.se", 2),
]

# Subordinates to add (excluding localhost:8080)
SUBORDINATES = [
    "https://fakerp0.labb.sunet.se",
    "https://fakeop0.labb.sunet.se",
    "https://fakerp1.labb.sunet.se",
]

FORCED_METADATA_FOR_FAKEOP0 = """{
  "openid_provider": {
    "application_type": "mutant",
    "system": ["py", "rust"],
    "subject_types_supported": ["pairwise", "public", "e2e"]
  },
  "extra_field": "extra_value"
}"""


def slow_type(page: Page, selector: str, text: str, delay: int = 50):
    """Type text slowly for video visibility."""
    page.click(selector)
    page.type(selector, text, delay=delay)


def wait_and_click(page: Page, selector: str, wait_time: float = 0.5):
    """Wait a bit then click for video visibility."""
    time.sleep(wait_time)
    page.click(selector)


def login(page: Page):
    """Login to the admin UI."""
    print("Logging in...")
    page.goto("http://localhost:5173/login")
    time.sleep(2)

    # Fill login form
    username_input = page.locator('input[placeholder="Enter your username"]')
    password_input = page.locator('input[placeholder="Enter your password"]')

    username_input.click()
    username_input.type("kushal", delay=80)
    time.sleep(0.3)

    password_input.click()
    password_input.type("redHat1234", delay=80)
    time.sleep(0.5)

    # Click login button
    page.click('button[type="submit"]')
    time.sleep(2)

    # Wait for redirect to home
    page.wait_for_url("http://localhost:5173/", timeout=10000)
    print("Logged in successfully")


def regenerate_entity_config(page: Page):
    """Click the Entity Configuration button in sidebar."""
    print("Regenerating entity configuration...")
    time.sleep(0.5)

    # Click the regenerate button
    page.click("button.server-btn")
    time.sleep(2)

    # Wait for success message
    page.wait_for_selector(".server-message--success", timeout=10000)
    time.sleep(1.5)
    print("Entity configuration regenerated")


def create_trust_mark_types(page: Page):
    """Create trust mark types through the UI."""
    print("Creating trust mark types...")

    # Navigate to trust mark types
    page.click('a[href="/trustmark-types"]')
    time.sleep(1)

    for i, tmt in enumerate(TRUST_MARK_TYPES):
        print(f"  Creating TMT: {tmt['tmtype']}")

        # Click create button
        page.click('button:has-text("Add Trust Mark Type")')
        time.sleep(0.8)

        # Fill tmtype (required, no default)
        tmtype_input = page.locator('input[placeholder="https://example.com/trustmarks/member"]')
        tmtype_input.click()
        tmtype_input.type(tmt["tmtype"], delay=30)
        time.sleep(0.3)

        # Only change valid_for if different from default (8760)
        if tmt["valid_for"] != "8760":
            valid_for_input = page.locator('input[type="number"]').first
            valid_for_input.click(click_count=3)  # Select all
            valid_for_input.type(tmt["valid_for"], delay=50)
            time.sleep(0.3)

        # Only change renewal_time if different from default (48)
        if tmt["renewal_time"] != "48":
            renewal_time_input = page.locator('input[type="number"]').nth(1)
            renewal_time_input.click(click_count=3)  # Select all
            renewal_time_input.type(tmt["renewal_time"], delay=50)
            time.sleep(0.3)

        # Submit
        page.click('.ir-modal__footer button:has-text("Create")')
        time.sleep(1.5)

        # Wait for modal to close
        page.wait_for_selector(".ir-modal", state="hidden", timeout=5000)
        time.sleep(0.5)

    print("Trust mark types created")


def create_trust_marks(page: Page):
    """Create trust marks through the UI."""
    print("Creating trust marks...")

    # Navigate to trust marks
    page.click('a[href="/trustmarks"]')
    time.sleep(1)

    for domain, tmt_index in TRUST_MARKS:
        print(f"  Creating TM for: {domain} (TMT {tmt_index})")

        # Click create button
        page.click('button:has-text("Issue Trust Mark")')
        time.sleep(0.8)

        # Select trust mark type from dropdown
        page.click(".form-select")
        time.sleep(0.3)
        page.select_option(".form-select", str(tmt_index))
        time.sleep(0.3)

        # Fill domain
        domain_input = page.locator('input[placeholder="https://example-rp.com"]')
        domain_input.click()
        domain_input.type(domain, delay=25)
        time.sleep(0.3)

        # Submit
        page.click('.ir-modal__footer button:has-text("Issue Trust Mark")')
        time.sleep(1.5)

        # Wait for modal to close
        page.wait_for_selector(".ir-modal", state="hidden", timeout=5000)
        time.sleep(0.5)

    print("Trust marks created")


def create_subordinates(page: Page):
    """Create subordinates through the UI using Fetch Config."""
    print("Creating subordinates...")

    # Navigate to subordinates
    page.click('a[href="/subordinates"]')
    time.sleep(1)

    for i, entity_id in enumerate(SUBORDINATES):
        print(f"  Creating subordinate: {entity_id}")

        # Click create button
        page.click('button:has-text("Add Subordinate")')
        time.sleep(0.8)

        # Fill entity ID
        entity_input = page.locator('input[placeholder="https://example-rp.com"]')
        entity_input.click()
        entity_input.type(entity_id, delay=25)
        time.sleep(0.5)

        # Click Fetch Config button
        page.click('button:has-text("Fetch config")')
        time.sleep(2)

        # Wait for fields to be populated
        page.wait_for_function(
            "document.querySelector('.cm-content')?.textContent?.length > 10", timeout=10000
        )
        time.sleep(1)

        # For the first subordinate, demonstrate JSON error and Format button
        if i == 0:
            print("    Demonstrating JSON error and Format button...")

            # Find the first CodeMirror editor (metadata)
            metadata_editor = page.locator(".ir-json-editor").first
            cm_content = metadata_editor.locator(".cm-content")

            # Click and go to beginning
            cm_content.click()
            time.sleep(0.3)
            page.keyboard.press("Control+Home")
            time.sleep(0.2)

            # Type invalid JSON at the start
            page.keyboard.type("{invalid", delay=100)
            time.sleep(1.5)

            # Show the error (pause for video)
            time.sleep(1)

            # Delete the invalid part
            page.keyboard.press("Control+Home")
            time.sleep(0.2)
            for _ in range(8):  # "{invalid" is 8 chars
                page.keyboard.press("Delete")
                time.sleep(0.05)
            time.sleep(0.5)

            # Click Format button to fix formatting
            format_btn = metadata_editor.locator('button:has-text("Format")')
            format_btn.click()
            time.sleep(1)
            print("    JSON error fixed with Format button")

        # For fakeop0, add forced_metadata
        if entity_id == "https://fakeop0.labb.sunet.se":
            print("    Adding forced_metadata...")

            # Find the forced_metadata editor (second one)
            forced_metadata_editor = page.locator(".ir-json-editor").nth(1)
            fm_content = forced_metadata_editor.locator(".cm-content")

            # Click and select all
            fm_content.click()
            time.sleep(0.3)
            page.keyboard.press("Control+a")
            time.sleep(0.2)

            # Type simpler forced metadata (single line to avoid issues)
            page.keyboard.type('{"openid_provider": {"application_type": "mutant"}}', delay=20)
            time.sleep(0.5)

            # Format it
            format_btn = forced_metadata_editor.locator('button:has-text("Format")')
            format_btn.click()
            time.sleep(1)

        # Scroll down to see the submit button
        page.evaluate("document.querySelector('.ir-modal__body').scrollTop = 9999")
        time.sleep(0.5)

        # Submit
        page.click('.ir-modal__footer button:has-text("Add Subordinate")')
        time.sleep(2)

        # Wait for modal to close
        page.wait_for_selector(".ir-modal", state="hidden", timeout=10000)
        time.sleep(0.5)

    print("Subordinates created")


def main():
    with sync_playwright() as p:
        # Launch browser with video recording
        browser = p.chromium.launch(
            headless=False,
            slow_mo=100,  # Slow down actions for visibility
        )

        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir="/home/kdas/code/inmor/videos/",
            record_video_size={"width": 1920, "height": 1080},
            ignore_https_errors=True,
        )

        page = context.new_page()

        try:
            # Step 1: Login
            login(page)

            # Step 2: Regenerate entity configuration (using sidebar button)
            regenerate_entity_config(page)

            # Step 3: Create trust mark types
            create_trust_mark_types(page)

            # Step 4: Create trust marks
            create_trust_marks(page)

            # Step 5: Create subordinates with Fetch Config
            create_subordinates(page)

            # Final pause to show the result
            print("Demo complete! Showing final state...")
            time.sleep(3)

        except Exception as e:
            print(f"Error during recording: {e}")
            raise
        finally:
            # Close context to save video
            context.close()
            browser.close()

        print("\nVideo saved to /home/kdas/code/inmor/videos/")


if __name__ == "__main__":
    main()
