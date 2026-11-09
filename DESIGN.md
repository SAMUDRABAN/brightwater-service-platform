# Brightwater office design

The design takes the restrained application frame, quiet borders and clear information hierarchy of ElevenLabs as a reference. Brightwater’s supplied logo, colours and typography remain the visual identity. No ElevenLabs logos or proprietary interface assets are copied.

## Tokens and structure

| Token | Value / use |
| --- | --- |
| Navy | `#1B3A5C`: headings, active navigation and brand |
| Deep navy | `#0F2238`: body text and text on orange buttons |
| Flame orange | `#F28C28`: limited primary actions; well below 10% of a normal page |
| Water blue | `#2A6FAE`: links, information and capacity |
| Mist / line | `#EAF1F7` / `#DDE3EA`: selection, subdued surfaces and borders |
| Slate | `#5B6B7A`: secondary text |
| Emergency red | `#C8372D`: gas/CO emergency presentation only |
| Typography | Supplied Manrope heading family; Inter body family. Locally hosted Latin WOFF2, with bundled SIL licences. Compact application type scale and generous line height. |
| Layout | 240px workspace rail; 65px header; left-aligned content; 8px-derived spacing; 7–12px component radii. |

```text
┌──────────────┬────────────────────────────────────────────┐
│ Brand / team │ Breadcrumb                Customer search │
│              ├────────────────────────────────────────────┤
│ Overview     │ Morning overview           Calling status │
│ Follow-ups   │ Campaign metrics: called / reached / ...  │
│ Diary        │                                            │
│ Customers    │ Prioritised follow-up queue │ Priorities    │
│ Calls        │                             │ Diary space   │
│ Controls     │ Booked yesterday            │               │
│              │                                            │
│ Personal     └────────────────────────────────────────────┤
│ account      │ Company / fictional-workspace notice      │
└──────────────┴────────────────────────────────────────────┘
```

Sarah’s queue is the primary work area, rather than a decorative analytics hero. Neutral calling status is distinct from an emergency. Engineering tests are visibly labelled and excluded from campaign metrics. Empty results explain the next useful action; unavailable quality measurements remain unavailable.

Below 760px navigation becomes a horizontal strip and content becomes one column. Wide tables and diary grids scroll inside their panels; they do not expand the page. Visible focus, semantic headings, form labels, table captions, reduced-motion handling and real pending/error states are part of the implementation.

## Review decisions

The earlier large navy metric band, symbolic text icons and decorative sidebar slogans have been removed. Orange is used for deliberate actions with dark text. The supplied SVG wordmark is used without recolouring or redrawing; no stock photograph is presented as a named staff member. Typography and icons support reading records rather than turning the CRM into a marketing page.
