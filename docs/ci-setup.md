# Branch Protection & CI Setup Guide

This guide provides step-by-step instructions for configuring branch protection rules in the GitHub web interface for the `main` branch of this repository.

> [!IMPORTANT]
> These settings must be applied manually by a repository administrator in GitHub Settings. They cannot be automated via standard git commits or workflow files alone.

---

## Prerequisites

Before configuring the status check requirement, make sure the `CI` workflow has run at least once on GitHub (either on a push or a pull request) so that GitHub detects the `verify` job.

---

## Step-by-Step GitHub Configuration

### 1. Open Branch Protection Settings

1. On GitHub, navigate to the repository: `https://github.com/shreyanshagrawal/justAbyte`.
2. Click the **Settings** tab in the top navigation bar.
3. In the left sidebar under the **Code and automation** section, click **Branches**.
4. Click the **Add branch ruleset** button (or **Add branch protection rule** if using legacy branch protection).
5. In the **Branch name pattern** field, enter:
   ```text
   main
   ```

---

### 2. Require the "verify" Job to Pass Before Merging

1. Under **Protect matching branches**, locate and check **Require status checks to pass before merging**.
2. Check the sub-option **Require branches to be up to date before merging** (ensures PR branch is tested against the latest `main`).
3. In the search box labeled **Status checks that are required**, type:
   ```text
   verify
   ```
4. Click `verify` in the search dropdown results to add it as a required check.

---

### 3. Require Approvals & Dismiss Stale Approvals

1. Check **Require a pull request before merging**.
2. Set **Required approvals** to at least **1** (or check **Require approvals** and specify `1`).
3. Check the checkbox for **Dismiss stale pull request approvals when new commits are pushed**.
   - _Why_: This ensures that if new code is pushed after a review, a fresh re-review is required before merging.

---

### 4. Block Force-Pushes to `main`

1. Scroll down to the **Rules** section.
2. Ensure that **Allow force pushes** remains **unchecked** (disabled).
   - If using GitHub Rulesets, toggle **Block force pushes** to **Enabled**.
   - _Why_: This prevents overwriting commit history on the production branch.

---

### 5. Save Changes

1. Scroll to the bottom of the page.
2. Click **Create** (or **Save changes**).
3. If prompted by GitHub, enter your GitHub password or two-factor authentication code to confirm administrator privileges.

---

## Verification Checklist

Once configured, verify that your branch protection rules for `main` show:

- [ ] Status check `verify` is required before merge.
- [ ] At least 1 approving review is required.
- [ ] Stale approvals are dismissed upon new commits.
- [ ] Force pushes to `main` are blocked.
