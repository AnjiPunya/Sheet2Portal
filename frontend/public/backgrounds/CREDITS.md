# Dashboard background images

Served locally from this folder (no runtime dependency on any image host).
Each domain has three widths (768 / 1280 / 1600 px, cropped to 2.4:1,
progressive JPEG) used as a responsive `srcset`. The mapping from business
domain to these files lives in `frontend/src/lib/backgrounds.ts`.

| Files | Domain | Source | License |
|---|---|---|---|
| `construction-*.jpg` | Real estate & construction | Unsplash — https://images.unsplash.com/photo-1541888946425-d81bb19240f5 | [Unsplash License](https://unsplash.com/license) (free commercial use, attribution not required) |
| `aquaculture-*.jpg` | Aquaculture | "Louisiana Catfish Ponds" by U.S. Department of Agriculture — https://commons.wikimedia.org/wiki/File:Louisiana_Catfish_Ponds_k4724-7.jpg | [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/) — **attribution required**; cropped and resized. Credit is shown on the dashboard banner. |
| `retail-*.jpg` | Retail & inventory | Unsplash — https://images.unsplash.com/photo-1578916171728-46686eac8d58 | Unsplash License |
| `agriculture-*.jpg` | Agriculture | Unsplash — https://images.unsplash.com/photo-1500382017468-9049fed747ef | Unsplash License |
| `healthcare-*.jpg` | Healthcare | Unsplash — https://images.unsplash.com/photo-1538108149393-fbbd81895907 | Unsplash License |
| `generic-*.jpg` | Generic fallback | Unsplash — https://images.unsplash.com/photo-1486406146926-c627a92ad1ab | Unsplash License |

## Adding a domain

1. Add `<domain>-768.jpg`, `<domain>-1280.jpg`, `<domain>-1600.jpg` here (2.4:1 crop).
2. Add an entry to `BACKGROUNDS` in `frontend/src/lib/backgrounds.ts` (record the credit if the license requires one).
3. Add its keywords to `DOMAIN_KEYWORDS` in `backend/app/services/analysis/domain.py`.
4. Add a row to this table.
