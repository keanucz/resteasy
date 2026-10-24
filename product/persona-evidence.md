# Persona evidence: older adults living alone, at night

Compiled by Adam's Claude, Fri 23 Oct 2026, from web research. For the pitch, Devpost write-up and
Q&A. Each claim lists its source and how strong it is. **Strength:** strong = government data or
peer-reviewed study; medium = large survey or official report; weak = industry survey, small
study, or secondhand summary.

## TL;DR for the pitch

- **16 million** Americans 65+ live alone, about 1 in 4. Among women 75+, it's **42%**. (ACL/Census)
- About **1 in 4** older adults falls each year. Falls killed **43,000** older Americans in 2024,
  and the death rate is up **21% since 2018**. (CDC, NSC)
- In a cohort of people over 90, **82% of falls happened when the person was alone**, 80% of fallers
  couldn't get up, and call alarms were in most homes but **rarely used**. (Fleming & Brayne, BMJ)
- Only **18%** of medical-alert users wear their device all the time. (The Senior List, 2026)
- **75%** of adults 50+ want to stay in their own homes. (AARP 2024)
- Older adults avoid asking for help so they don't **burden** their families, even when those
  families are close. (JAGS 2018 focus groups; BMC Geriatrics 2022)
- California: **~10M** older adults by 2030 (25% of the state). **647,000** Californians 65+ who live
  alone can't cover basic costs (UCLA Elder Index).

## The pillow's chain: night trip → fall → pillow stays empty → family alerted

Each step of the Night Watch flow, and what evidence backs it.

| Step | Evidence | Source | Strength |
|---|---|---|---|
| **1. She gets up at night** | Nocturia (waking to urinate) is linked to a ~1.2× higher fall risk (9 longitudinal studies). Getting up 3+ times a night: +28% risk of a new fall within 3 years in a community cohort | [Chen et al., systematic review & meta-analysis](https://uroluts.uroweb.org/publication/the-impact-of-nocturia-on-falls-and-fractures-a-systematic-review-and-meta-analysis/); [community cohort (PMC, pmid 20456212)](https://pmc.ncbi.nlm.nih.gov/articles/pmid/20456212) | strong (association, not causation) |
| **2. The trip is when falls happen** | 34% of falls in adults 60+ were toileting-related, ≥44% of those at night, peaking 11pm–1am; almost half of night falls were at the bedside | [Rose et al., Australas J Ageing 2019](https://onlinelibrary.wiley.com/doi/10.1111/ajag.12696) | medium (hospital, not home) |
| | Older adults fall going to the bathroom at night because of low light (this is the case for the path light) | [2022 field study, PMC9520131](https://pmc.ncbi.nlm.nih.gov/articles/PMC9520131) | medium |
| **3. She's alone and can't get up** | 82% of falls happened when the person was alone; 80% of fallers couldn't get up after at least one fall | [Fleming & Brayne, BMJ 2008](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2590903/) | strong |
| **4. Her alarm doesn't help** | Call alarms were in most homes but rarely activated during falls | same | strong |
| **5. Time on the floor is what hurts** | Lying on the floor 1h+ (30% of fallers) was strongly associated with serious injury, hospital admission and moves into long-term care | same | strong |
| | Long lies cause rhabdomyolysis, pressure injury, dehydration, hypothermia, pneumonia; 60% of older fallers with a 1h+ long lie were readmitted for a fall within a year | [Scoping review, long-lie therapy](https://magazine.sciencepod.net/?p=435980); [RCNI systematic review 2025](https://journals.rcni.com/nursing-older-people/evidence-and-practice/exploring-the-concept-of-a-long-lie-after-a-fall-to-inform-clinical-pathways-in-prehospital-services-a-systematic-literature-review-nop.2025.e1505/pdf) | medium |
| **6. An empty bed is a usable signal** | UK councils already issue "bed occupancy sensors" to older people living alone: a mattress pad raises an alert if the person leaves bed and doesn't return within a set time, "indicating a possible fall", and can switch on lights | [Tunstall bed/chair occupancy sensor](https://www.tunstall.co.uk/our-products/product-catalogue/bed-chair-occupancy-sensor/); [Medway Council telecare](https://www.medway.gov.uk/directory_record/48951/telecare_bedchair_occupancy_sensor) | medium (established practice, not a trial) |
| | Under-bed sensor in a seniors' residence detected high-risk residents leaving bed at night and alerted staff, removing the need for hourly room checks | [Bruyère/Carleton Sleepsense pilot 2023](https://carleton.ca/sam3/2023/toch-sleepsense-technology-enables-retirement-home-staff-to-monitor-overnight-bed-exits-for-seniors-with-real-time-alerts) | medium (care home) |
| | Bed sensors vary a lot: one had 0–2.7% entry/exit errors, another missed 59% of short exits | [Wallace et al. 2020, eTELEMED](https://carleton.ca/sam3/wp-content/uploads/etelemed_2020_3_220_40094.pdf) | medium |
| **7. Family gets the alert** | US PERS services already route non-emergencies to designated responders who are family, neighbours or friends | [OSF HealthCare personal response systems](https://www.osfhealthcare.org/services/home-care/home-medical-equipment/equipment-supplies/personal-response-systems) | weak (provider page) |
| | 63M family caregivers in the US | [AARP/NAC 2025](https://www.aarp.org/press/releases/2025-07-24-new-report-reveals-crisis-point-for-americas-63-million-family-caregivers.html) | medium |

### The pitch, in one line per step

"She gets up at night (that's when falls happen) → she's alone, can't get up, and doesn't press the
button → every hour on the floor makes it worse → **her pillow notices she hasn't come back** → it
checks in with her, then tells her daughter. No wearable, no button."

### What's ours, not the literature's

- **Bed-exit + no-return is proven *practice*** (UK telecare, care homes), but we found **no
  peer-reviewed trial** showing it reduces long lies or harm for people living at home. Say
  "councils already prescribe bed sensors for exactly this; we added a voice check-in and family
  routing", not "proven to save lives".
- **Existing systems alert a call centre or staff.** We found no study of alerts going straight
  to family. That's our design choice (least intrusive first, matches the burden findings).
- **Why a pillow and not a mattress pad:** *not* because the hardware is cheaper. A basic US bed-exit
  pad + pager is $45–120 ([Walmart listings](https://www.walmart.com/ip/17327397), [AliMed $56 pad](https://www.alimed.com/products/skil-care-overmattress-bed-sensor-pad)),
  similar to our parts cost. The difference is everything around the sensor:
  - **Access:** in the UK, bed sensors are an add-on that usually needs a council assessment
    ([Perth & Kinross](https://www.pkc.gov.uk:443/article/14642/Telecare-service), [Coventry](https://www.coventry.gov.uk/care-support/telecare/print)),
    i.e. typically after something has already gone wrong.
  - **Ongoing cost:** UK councils charge £1.40–6.77/week for the sensor on top of a £4–7/week
    lifeline ([Derby 2024](https://derby.gov.uk/media/derbycitycouncil/contentassets/documents/healthandsocialcare/adultsocialcare/ylyc/Charges-for-telecare-April-2024.pdf), [Bracknell Forest](https://www.bracknell-forest.gov.uk/health-and-social-care/forestcare/range-sensors/bed-or-chair-occupancy-sensor), [Haringey](https://haringey.gov.uk/node/7143)),
    roughly £300–700/year. Our pitch is no subscription.
  - **What happens after the alert:** a pad beeps a pager in the house, or calls a call centre.
    The pillow talks to her first, then picks the family member who's awake.
  - **Reach:** ~1.8M people in the UK use any telecare, 1.3M of them at home
    ([Centre for Care 2025, citing DHSC 2023](https://centreforcare.ac.uk/wp-content/uploads/2025/06/On-hold_KH_GW_May-2025_FINAL.pdf)),
    out of roughly 13M people 65+ in the UK (ONS order of magnitude, not looked up here; verify
    before quoting). Every user gets a pendant; bed sensors are a
    smaller, assessed subset, and we found no national count of them. So most older people
    living alone, including those with no diagnosis yet, have no bed-exit detection at all.
- **Honest weakness:** a pillow is a *worse* occupancy sensor than a mattress pad. People move off
  their pillow in their sleep, so "head off pillow" ≠ "out of bed". Mitigations: the no-return
  timer is long (20 min), the IMU and sound sensor can tell a roll from a get-up, and the voice
  check-in comes before any family alert. Have this answer ready for judges.
- **Accuracy matters.** Wallace et al. show cheap sensors miss short exits. Our no-return timer
  (20 min) only needs the long absence, which is the easier case; mention it if a judge asks about
  false alarms. The "I'm fine" key/tap and the voice check-in are what stop a false alarm from
  reaching family.
- **Don't quote** "half of people who lie 1h+ die within 6 months" (Wild 1981). It's widely
  repeated but we couldn't trace it to the primary source; use Fleming & Brayne instead.

## (a) Older adults living alone are a large, specific market

| Claim | Number | Source | Strength |
|---|---|---|---|
| Older adults living alone (US) | 16.2M, 28% of community-dwelling 65+ (5.7M men, 10.5M women) | [ACL 2023 Profile of Older Americans](https://acl.gov/sites/default/files/Profile%20of%20OA/ACL_ProfileOlderAmericans2023_508.pdf) | strong |
| Women 75+ living alone | 42% | same | strong |
| Share of 65+ living alone (Pew, all settings) | 26% in 2023, down from 29% in 1990 | [Pew Research, Dec 2025](https://www.pewresearch.org/short-reads/2025/12/04/a-smaller-share-of-older-us-adults-live-alone-today-than-in-1990/) | strong |
| Want to age in place | 75% of 50+ want to stay in their home, 73% in their community | [AARP 2024 Home & Community Preferences](https://www.aarp.org/press/releases/2024-12-10-new-aarp-report-majority-adults-50-plus-age-place-policies-communities-catch-up.html) | medium |
| Social isolation | about 1 in 4 community-dwelling 65+ are socially isolated; linked to early death, dementia, heart disease | [National Academies 2020](https://www.nationalacademies.org/news/health-care-system-underused-in-addressing-social-isolation-loneliness-among-seniors-says-new-report) | strong |
| Falls | more than 1 in 4 older adults fall each year; 43,020 fall deaths (65+) in 2024 | [NSC Injury Facts](https://injuryfacts.nsc.org/home-and-community/safety-topics/older-adult-falls/) | strong |
| Fall death rate trend | 64.7 → 78.4 per 100k older adults, 2018 → 2024 (+21%) | [CDC Older Adult Falls Data](https://www.cdc.gov/falls/data-research/index.html) | strong |
| Cost of falls | ~$80B/yr non-fatal fall costs (2020), projected $101B by 2030; Medicare pays 67% | [NCOA](https://www.ncoa.org/article/get-the-facts-on-falls-prevention) | medium |
| Falls when alone | 82% of falls (217/265) happened when the person was alone; 30% of fallers lay on the floor 1h+; long lies predicted hospital admission and moves into long-term care | [Fleming & Brayne, BMJ 2008](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2590903/) (n=110, aged 90+, UK) | strong (UK, very old) |
| Night-time toileting falls | 34% of falls in adults 60+ were toileting-related, at least 44% of those at night, peaking 11pm–1am; half at the bedside | [Rose et al., Australas J Ageing 2019](https://onlinelibrary.wiley.com/doi/10.1111/ajag.12696) | medium (hospital, not home) |
| Family caregivers | 63M US family caregivers, +45% in a decade; avg age 51 | [AARP/NAC Caregiving in the US 2025](https://www.aarp.org/press/releases/2025-07-24-new-report-reveals-crisis-point-for-americas-63-million-family-caregivers.html) | medium |
| PERS market (US) | $2.49B (2022), projected $4.44B by 2028 | [Arizton](https://www.arizton.com/market-reports/us-personal-emergency-response-systems-market) | weak (market-research firm) |

### California and the Bay Area

| Claim | Number | Source | Strength |
|---|---|---|---|
| California older adults by 2030 | ~10M (25% of the state) | [CA Master Plan for Aging](https://mpa.aging.ca.gov/) | medium |
| CA 65+ living alone who can't afford basic needs | 647,000 in 2023 (+19% since 2015); basic costs for a single renter are $32,100 vs a federal poverty line of $14,580 | [UCLA Elder Index 2025](https://healthpolicy.ucla.edu/newsroom/blog/california-elder-index-fact-sheets-2025-update) | strong |
| San Francisco 60+ | 169,189 adults 60+ (2018) | [SF DAAS Dignity Fund needs assessment](https://sfhsa.org/sites/default/files/media/document/migrated/DAAS%20Com_Agenda%20Item%20A%20DFCNA%20Executive%20Summary0418%20%285.2.18%29.pdf) | medium (dated) |
| San Francisco households that are a 65+ person alone | ~11.3% of all SF households; highest in Chinatown and Japantown | [Mission Local, Dec 2022 (ACS 5-yr)](https://missionlocal.org/2022/12/elderly-chinatown-living-alone/) | medium |
| SF vs the rest of California | SF older adults are more likely to live alone than in other California cities | [SF DAS infographic (ACS 2019)](https://www.sfhsa.org/sites/default/files/media/document/migrated/Image_DAS%20Infographic_Demographics_English_2021.pdf) | medium |
| Bay Area region | 28–44% of households include someone 65+; in some counties nearly 1 in 5 older adults live alone. Marin: 23.3% of residents are 65+, and 16.5% of seniors live alone | [Local News Matters, Sep 2025](https://localnewsmatters.org/2025/09/23/the-geography-of-aging-housing-income-and-independence-across-the-greater-san-francisco-bay-area-region/) | medium |

**Gap:** no single nine-county Bay Area figure for 65+ living alone. To get one, pull ACS table
B09021 / S1101 for the nine counties (about 20 min), or use the UCLA Elder Index county dashboards.

## (b) Feeling like a burden, and tech that sits outside the routine

| Claim | Finding | Source | Strength |
|---|---|---|---|
| Burden drives refusing help | Focus groups with 68 community-dwelling adults 65+: reluctance to accept home support came from feeling burdensome, lack of trust, fear of losing control. Some reframed independence as "interdependence" | [JAGS 2018 (PubMed 30155882)](https://pubmed.ncbi.nlm.nih.gov/30155882/) | medium (qualitative) |
| Burden even with close family | Older adults living alone "prefer to overcome difficulties on their own rather than seek help, in order to avoid being a burden", even with close family or friends | [BMC Geriatrics 2022, urban China](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9241305/) | medium (qualitative, not US) |
| Burden linked to unmet care needs | Care recipients' concerns about being a burden linked to unmet care needs | [Weill Cornell, "Care Recipient Concerns About Being a Burden and Unmet Needs for Care"](https://vivo.weill.cornell.edu/display/pubid30480145) | medium (abstract only, not read in full) |
| Alarms exist but aren't used | Call alarms were present in most homes but rarely activated during falls | [Fleming & Brayne, BMJ 2008](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2590903/) | strong |
| Wearables aren't worn | Only 18% of medical-alert users wear it all the time; 64% don't wear it in the shower | [The Senior List 2026](https://theseniorlist.com/research/medical-alert-device-consumer-usage-study) (n=2,695) | weak (industry survey) |
| Wear rate even in a study | High-fall-risk adults with a fall-detecting pendant wore it on a median of 68% of days | [PERS pilot, PMC12761017](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12761017/) (n=20) | weak (small pilot) |
| Who decides when to wear | Frail women living alone actively decided when to wear the pendant and whether to press it | [Hasselt workshop paper (cites Fleming & Brayne and a 2005 qualitative study)](https://documentserver.uhasselt.be/bitstream/1942/19725/1/IHS%20workshopfinal.pdf) | weak (secondary) |
| What drives fall-tech adoption | Comfort, reliance on human care, attitudes to tech, cost, expectations (30 older adults + 29 family members) | [PMC11334405, 2024](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11334405/) | medium |

### What this does and doesn't support

- **Supported:** feeling like a burden is a well-documented reason older adults don't ask for help.
  Pendants and call alarms fail at the moment that matters: not worn, not pressed, especially when
  the person is alone.
- **Our inference, not a finding:** a pillow works better *because* it's already part of the
  bedtime routine and needs no wearing or pressing. We found no study comparing ambient bedding
  sensors with wearables. In the pitch, say "the evidence shows wearables aren't worn and alarms
  aren't pressed, so we put the sensing in something she already uses every night."
- **No direct evidence** for "reluctant to call family *at night*" specifically. The burden
  literature is about help in general. Frame the night angle as: "she won't wake her daughter at
  2am, and she won't press the button" (ties burden + non-use together), and keep it a hypothesis
  if a judge asks.
- **Weak spots to avoid quoting:** the 18% wear stat is an industry survey; PERS market sizes are
  from market-research press releases and conflict with each other.
