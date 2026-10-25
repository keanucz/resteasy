# Research angles beyond the market

Compiled by Adam's Claude, Fri 23 Oct 2026. Complements `persona-evidence.md` (market, burden,
night-fall chain) and `academic-evidence.md` (Keanu's: bed-exit accuracy, ambient vs wearable,
voice assistants, night lighting, telecare false alarms; not repeated here). Strength: strong =
government data / peer-reviewed; medium = large survey, official report; weak = vendor, blog,
single news piece.

## TL;DR: ideas this research suggests

1. **"Mum's up" morning signal.** Police "Are You OK?" programs phone people living alone at 8am and
   escalate if there's no answer. The pillow can do that passively: when she gets up in the
   morning, the owner gets "Mum's up ☀". Daily reassurance with no call and no burden.
2. **Sleeping-tablet mode.** ~12% of 65+ take a sleep aid most nights; sedatives raise fall and hip
   fracture risk. A setup question ("Do you take something to help you sleep?") shortens the
   no-return timeout. Never advises on medication (Guardian).
3. **Light and touch first, voice second.** About half of people 75+ have disabling hearing loss and
   hearing aids come out at night. Confirms the earlier design: the path light and pillow vibration
   are the first channel, and voice comes after.
4. **Speak her language.** SF's older adults are unusually likely to have limited English and live
   alone. Cartesia supports Mandarin and Spanish. A Mandarin check-in in the demo hits Cartesia's
   accessibility criterion.
5. **Cold-bedroom nudge.** Older adults feel the cold less; guidance is ≥18 °C (65 °F) in occupied
   rooms. The KY-001 sensor gives the Environment agent a real job.
6. **No battery in the pillow, and safety that survives the cloud.** Zeeq, the best-known smart
   pillow, lost its features when the company stopped supporting the app. Lithium batteries in
   bedding are a fire risk. So: sensors only in the pillow, and the base keeps the path light and a
   local check-in working if the server is unreachable (production path, not the demo).
7. **Wording matters legally.** Say "notices she hasn't come back and checks in", not "detects
   falls" (FDA general-wellness line). Never store raw audio (California all-party consent law).

## 1. Competitors and their gaps

| Product | What it does | Gap the pillow fills | Source | Strength |
|---|---|---|---|---|
| Apple Watch fall detection | Impact-based fall detection + auto-call | Usually **on the charger at night**; a slide out of bed is low-impact | [Calcalist](https://www.calcalistech.com/ctech/articles/0,7340,L-3746361,00.html), [consumer guide](https://taking.care/blogs/resources-advice/alternatives-to-apple-watch-fall-detection) | weak (commentary, no study) |
| Nobi smart lamp | Ceiling/lamp camera-like sensing; on a fall, **asks if she's OK, then calls contacts** | Mainly care homes; ~$2,500 per apartment + $19/mo (2021 pricing). Already does voice check-in, so we can't claim that's new | [TechHive](https://www.techhive.com/article/579134/the-nobi-smart-lamp-can-detect-when-a-person-falls-in-their-home-and-will-call-for-assistance.html), [Medical Device Network 2025](https://www.medicaldevice-network.com/news/nobi-secures-e35m-to-advance-ai-powered-fall-detection-technology/) | medium |
| SafelyYou | Video fall detection + remote clinical support | Facilities and dementia, cameras | [CB Insights](https://www.cbinsights.com/company/nobi-smart-lamps/alternatives-competitors) | weak |
| Zeeq smart pillow (REM-Fit) | Sleep tracking, snore detection, speakers in the foam | **App support ended Dec 2021**; company closed in 2020. A cautionary tale: the smart features depended on one company's app | [LiveWorkSleep review](https://liveworksleep.com/zeeq-smart-pillow-review/), [GearBrain](https://www.gearbrain.com/smart-pillow-remfit-closes-coronavirus-2645603770.html) | weak |
| Police "Are You OK?" / R.U.O.K. programs | Automated daily call (e.g. 8am); no answer after 3 tries → police / contact | Daytime only, needs her to answer a phone, low enrolment (e.g. ~40 people countywide a year in) | [Salem MA](https://www.salemma.gov/node/244923), [Fuquay-Varina NC](https://www.fuquay-varina.org/875/R-U-OK-Program), [Laurinburg Exchange](https://www.laurinburgexchange.com/news/local/9951/program-ok-with-scotland-county-seniors), [El Dorado County CA (YANA)](https://www.eldoradocounty.ca.gov/Services/Assistance-Programs/Seniors/Senior-Services/YANA-You-Are-Not-Alone) | medium |

**Our position:** no camera, nothing to wear or charge, it's in the bed she already sleeps in, the
trigger is "hasn't come back", and family comes first. Check-in-then-escalate is proven by Nobi and
the police programs; we're the version for the night that needs no phone, camera or button.

## 2. Higher-risk subgroups within the persona

| Claim | Number | Source | Strength |
|---|---|---|---|
| Sleep aid use | 11.9% of 65+ use a sleep aid every night or most nights (CDC NCHS, 2020) | [Michigan Medicine summary](https://www.michiganmedicine.org/health-lab/sleep-aids-arent-safe-older-adults-1-3-still-take-them), [PMC7925354](https://pmc.ncbi.nlm.nih.gov/articles/PMC7925354) | strong |
| Sedatives and falls | Beers Criteria: avoid benzodiazepines (strong rec., high-quality evidence) and Z-drugs like zolpidem in older adults; impaired balance, gait, reaction time | [CMAJ](https://cmaj.ca/content/185/17/1499.full.pdf), [AAFP Choosing Wisely](https://www.aafp.org/pubs/afp/collections/choosing-wisely/25.html) | strong |
| Fracture risk | Benzodiazepine users: hip fracture odds ≈3.45× non-users (Brazilian older-adult cohort) | [Geriatrics, Gerontology and Aging 2023](https://doaj.org/article/e8d34bc7e6e54ce1a84737e8eb6808f1) | medium |
| Normal sleep in older age | More awakenings, mostly in the second half of the night; healthy older adults usually fall back asleep | [PMC3142094](https://pmc.ncbi.nlm.nih.gov/articles/PMC3142094) | strong |

Use: supports the personal baseline (waking is normal, so a learned "normal" beats a fixed rule)
and a sleeping-tablet setting that shortens the timeout. Never comment on the medication itself.

## 3. Hearing and the night

| Claim | Number | Source | Strength |
|---|---|---|---|
| Disabling hearing loss | ~25% of 65–74, ~50% of 75+ | [USF citing NIDCD](https://usf.edu/cbcs/csd/bolesta/patients/hearing-loss-facts.aspx) | medium (secondary; NIDCD figures vary 22–25% / 50–55%) |
| Hearing aid uptake | <30% of adults 70+ who could benefit have ever used them | [NIDCD](https://www.nidcd.nih.gov/health/statistics/use-hearing-aids-adults-hearing-loss) | strong |

Design consequences: light and vibration first; voice is low-pitched, slow and short, after a
chime; never rely on her hearing the base speaker from another room (escalate on silence).

## 4. Money: what the alternatives cost

| Option | Cost | Source | Strength |
|---|---|---|---|
| Assisted living (US median, 2024) | $5,900/month, $70,800/year, +10% in a year | [Genworth/CareScout 2024](https://investor.genworth.com/news-events/press-releases/detail/982/) | strong |
| Home health aide (US median, 2024) | $34/hour; $77,792/year | same | strong |
| Nursing home, private room | $10,646/month | same | strong |
| Nobi | ~$2,500 + $19/month (2021) | [TechHive](https://www.techhive.com/article/579134/the-nobi-smart-lamp-can-detect-when-a-person-falls-in-their-home-and-will-call-for-assistance.html) | weak (dated) |
| UK council bed sensor | ~£300–700/year incl. monitoring | see `persona-evidence.md` | medium |
| Medicare Advantage PERS benefit | PERS offered by 1,337 MA plans in 2022 (971 in 2021) | [Milliman 2022](https://milliman.com/-/media/milliman/pdfs/2022-articles/3-21-22_ma-supplemental-benefits.ashx) | medium |

Pitch math: long lies predict moves into long-term care (Fleming & Brayne, BMJ 2008). Delaying
one move into assisted living by a year is worth ~$70k to a family; the pillow costs a tiny fraction.
Production path: direct to adult children first; later Medicare Advantage supplemental benefits
and Area Agencies on Aging. California and San Francisco figures weren't in the free search results;
CareScout's map has them if we need a local number.

## 5. The owner (adult child) side

| Claim | Number | Source | Strength |
|---|---|---|---|
| Caregivers using remote monitoring | 13% (2020) → 25% (2025) | [AgeInPlaceTech on AARP 2025](https://www.ageinplacetech.com/blog/caregiving-us-2025-more-tech-not-much-caregivers-could-use) | medium |
| Interest in caregiving tech | 33% use it, 39% more are interested | [AARP 2025 tech trends](https://www.ageinplacetech.com/files/aip/2025-technology-trends-older-adults-caregiving.doi_.10.26419-2fres.00891.007.pdf) | medium |
| Older adults' trade-off | ~8 in 10 would give up some privacy so family knows they're safe, if it means staying home (Healthy@Home 2.0, date not confirmed) | [Rehab Pub](https://rehabpub.com/pain-management/technology/older-americans-are-more-open-to-caregiving-technology-study-finds/) | weak (older survey) |
| Distance | Caregivers 1h+ away report more physical and financial strain | [2020 NAC/AARP analysis, PMC11692659](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11692659/) | strong |

Supports the owner = setup-person decision: the buyer is a time-poor adult child, often at a
distance; what they want is to know she's OK without calling every day (hence "Mum's up").

## 6. Rules we need to respect

- **FDA general wellness (finalized Jan 2026):** low-risk products with wellness claims are under
  enforcement discretion; disease or detection claims ("detects insomnia") push a product toward
  being a medical device, and disclaimers don't fix it. Fall detection isn't addressed.
  → Say "notices she hasn't come back to bed and checks in", not "detects falls"; Guardian blocks
  medical language. ([Womble Bond Dickinson](https://www.womblebonddickinson.com/us/insights/blogs/fdas-2026-general-wellness-policy-and-what-it-means-manufacturers-wearable-devices), [Wireless Life Sciences](https://wirelesslifesciences.org/2026/01/general-wellness-vs-medical-device-in-2026-fda-rules-for-wearables-apps-and-claims/); medium, law-firm commentary)
- **California Penal Code §632:** recording a confidential conversation needs consent of all
  parties. → Listen only during an active check-in or hold-to-talk, never store raw audio, get the
  resident's consent at setup; visitors are a reason never to listen continuously.
  ([statute](https://california.public.law/codes/penal_code_section_632); strong. CCPA treatment of
  voice data not researched.)

## 7. Language access in the Bay Area

| Claim | Finding | Source | Strength |
|---|---|---|---|
| Limited English | 37% of SF seniors spoke English "not well" or "not at all" (ACS 2005, dated) | [SF DAAS 2010 needs assessment](https://sfhsa.org/sites/default/files/media/document/migrated/DAAS%20Consumer%20Advocacy%20Needs%20Assessment%20%282010%29.pdf) | medium (old) |
| Who | SF seniors are more likely than elsewhere in CA to be older, have limited English, and live alone; older Chinese women in Chinatown often live alone in single-room apartments and speak Cantonese or Mandarin | same; [OCPSC Region 3](https://ocpsc.ca.gov/region-3-story/) | medium |
| Cartesia languages | Sonic-3 lists Chinese and Spanish (and others); Cantonese not confirmed | [Cartesia docs](https://docs.cartesia.ai/build-with-cartesia/tts-models/latest) | strong (vendor docs) |

Demo idea: switch the check-in to Mandarin or Spanish live. Check Cantonese in Cartesia's full
language table before promising it.

## 8. Room temperature

- Guidance: keep occupied rooms ≥18 °C (65 °F), ~21 °C for older adults; heat the bedroom before
  bed; ability to sense cold falls with age ([HPSC Ireland](https://hpsc.ie/a-z/environmentandhealth/severeweatherevents/coldweather/coldweatheradviceforolderpeopleandtheirfamiliesandneighbours); medium).
- Older UK study: at-risk older people's bedrooms were far below WHO-recommended temperature
  ([BMJ 1987](https://www.bmj.com/content/295/6595/419); strong but old).
- → Environment agent: if the bedroom is <18 °C at bedtime, a gentle voice nudge; repeated cold nights
  go in the Morning Brief.

## 9. Physical build safety (Adam's build lane)

- Firefighters warn against charging devices under pillows or bedding: trapped heat can make
  lithium batteries overheat and ignite ([KX News](https://www.kxnet.com/news/state-news/charging-phones-under-pillows-could-cause-house-fire/amp/); weak). CPSC recalled a portable sleep machine in 2026
  for fire and burn hazards ([CPSC](https://www.cpsc.gov/Recalls/2026/Love-To-Dream-Recalls-Portable-Sleep-Machines-Due-to-Risk-of-Injury-from-Fire-and-Burn-Hazards); strong).
- → Confirms the rule in `CONTEXT.md`: only sensors in the pillow; battery, ESP32 and power in the
  base. Sensor pod in a removable, washable pocket; flat cable to the base.

## Gaps not filled

- No source on Alexa Together's shutdown reason (couldn't verify; don't cite).
- No current SF/Bay Area cost-of-care or limited-English figures (both need ACS / CareScout pulls).
- Whether FDA would treat "no-return" alerts as fall detection: needs regulatory counsel; avoid the
  claim instead.
