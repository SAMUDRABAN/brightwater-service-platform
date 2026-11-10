# Engineering conventions

There is no single UK-wide mandatory convention for Python identifiers, React filenames or software version numbers. This project follows its language ecosystems and established release practices. UK-specific presentation follows British English and the supplied client brand.

| Area | Convention |
| --- | --- |
| Client-facing language | British English, sentence case, clear verbs and short explanations. “Calling”, “diary”, “postcode” and “VAT” follow the brief. |
| Dates and time | ISO 8601 timestamps with offsets in APIs; UTC storage; `Europe/London` for calling policy and `en-GB` display. Tests cover summer and winter time. CSV timestamps are explicitly labelled UTC. |
| Prices | Integer pence in the database; GBP formatting in the interface. All brief service prices include VAT. No floating-point money calculations. |
| Telephone numbers | E.164 for approved destinations. UK campaigns and separately allowlisted India engineering tests remain distinct. Original assessment numbers are never dialled. |
| Source names | Python `snake_case`; TypeScript `camelCase`; components/types `PascalCase`; readable route and document filenames. Stable identifiers are not renamed for cosmetic consistency. |
| Versions | Semantic Versioning, currently `0.2.2` for an engineering candidate. Version metadata is checked and tags are `vX.Y.Z`. A version label is not a production qualification claim. |
| Data and permissions | PostgreSQL constraints and transactions, typed API validation, explicit staff roles, revocable sessions and immutable action history. |
| Delivery | Frozen dependencies, CI, focused commits, recorded checks, release notes and a rollback reference. Secrets and private caller artefacts stay outside source and Git history. |

## Guidance consulted

- [GOV.UK Service Manual: making source code open and reusable](https://www.gov.uk/service-manual/technology/making-source-code-open-and-reusable): separate credentials and document ownership/reuse. Its public-sector publication requirements do not make this confidential private assessment public.
- [GOV.UK Service Manual: naming your service](https://www.gov.uk/service-manual/design/naming-your-service): use names people can understand. This informs “Follow-ups”, “Customers” and “Diary & bookings”, rather than internal pipeline terminology.
- [GOV.UK Design System: tables](https://design-system.service.gov.uk/components/table/): appropriate table structure, headings and readable data. The implementation retains the client’s own brand rather than claiming GOV.UK branding.
- [GOV.UK style guide](https://www.gov.uk/guidance/style-guide/a-to-z): plain English and consistent UK presentation.
- [Semantic Versioning](https://semver.org/): release numbering.
- [Prettier installation guidance](https://prettier.io/docs/install): a pinned, local formatter and repeatable checks.

These are engineering references, not certifications or a claim that government service requirements apply to a private company. Automated checks and visual review are not a complete accessibility audit.
