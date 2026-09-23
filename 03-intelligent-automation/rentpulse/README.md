> **Part of [ai-portfolio](../../README.md)** · Evidence: *Personal project, shipped commercial product*
>
> **Category:** **Intelligent Automation**
>
> **Source code:** not published. RentPulse is a live commercial product, so this folder holds documentation only.

---

# RentPulse

**Live product:** [rentpulse.ie](https://www.rentpulse.ie) ·
[Chrome Web Store](https://chromewebstore.google.com/detail/rentpulse/fdnhmpfmjgophiliblfkenlkaplcmmmf)

## What it does

RentPulse is a Chrome extension for people looking to rent in Ireland. It watches
several Irish rental listing sites at once and sends a desktop notification as soon as a new
property that matches your filters (location, price range, bedrooms) goes live.

Good rentals are often gone within hours of listing. RentPulse turns "keep refreshing six
websites" into a single alert.

- **Free tier:** alerts across all monitored sites, no account needed.
- **Pro tier:** faster checks, several saved search profiles, and scam detection, billed monthly.
- **Privacy:** search preferences stay in the user's browser. No account is needed for the free tier.

## Architecture

Three deployable components, kept in one private repository:

```
┌──────────────────────────┐      ┌──────────────────────────┐
│  Chrome extension (MV3)  │─────▶│  Backend API (Node.js)   │
│  · user filters & state  │      │  · subscriptions          │
│  · background monitoring │      │  · account / entitlement  │
│  · desktop notifications │      └────────────┬─────────────┘
└──────────────────────────┘                   │
                                     ┌─────────┴─────────┐
┌──────────────────────────┐         │  Stripe  Supabase │
│  Marketing website       │         └───────────────────┘
└──────────────────────────┘
```

Design points:

| Concern | Approach |
|---|---|
| Resilience | Built to keep working when an individual listing site changes behaviour, with no new release needed |
| Privacy | User preferences held locally in the browser, not on a server |
| Payments | Real subscription billing through Stripe; paid features gated by the backend |
| Release discipline | Versioned releases through Chrome Web Store review, with a dedicated security-hardening release |
| Decisions | Recorded as decision documents alongside the code |

## Technology stack

| Layer | Technology |
|---|---|
| Extension | JavaScript · Chrome Manifest V3 (service worker, storage, notifications) |
| Backend | Node.js · Express |
| Payments | Stripe |
| Data / auth | Supabase |
| Build & quality | npm build pipeline · CI workflow · automated test suites for extension and backend |

## Scale

| | |
|---|---|
| Sources monitored | 6 Irish rental listing sites |
| Components | 3 (extension, backend, website) |
| Development history | 170+ commits |
| Automated tests | 185 (extension and backend) |
| Status | Live on the Chrome Web Store with free and paid tiers |

## What this demonstrates

End-to-end product delivery under real-world constraints: a public store listing, real
billing, platform review processes, versioned releases, and designing around platform
limits.

> **Note:** RentPulse contains **no AI or machine learning.** It is included as evidence
> of automation and product delivery, not as an AI project.
