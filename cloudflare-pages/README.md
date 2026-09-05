# Cloudflare Pages legal site

This folder is a standalone static site for public Terms of Service and Privacy
Policy URLs used by platform app reviews.

Deploy it on Cloudflare Pages with:

- Framework preset: None
- Root directory: `cloudflare-pages`
- Build command: none
- Output directory: `cloudflare-pages` (or `/` when the root directory is set)

Before publishing, replace the contact placeholders in `terms.html` and
`privacy.html` with a real support email and review the policy for the actual
service and business.

The React operator console is a separate Cloudflare Pages project built from
`console/`.
