# Academic evidence: does the design hold up?

Compiled by Keanu's Claude, Fri 23 Oct 2026, from open-access papers (PubMed Central, journal
pages). Complements `persona-evidence.md` (the "why"): this file covers the questions judges will
ask about the *design*. Strength: strong = RCT, systematic review or large cohort; medium = smaller
trial, observational or review of mixed quality; weak = pilot, qualitative or secondary report.

## TL;DR for Q&A

1. **"Bed alarms don't work, do they?"** In *hospitals*, a large trial found that more bed alarms
   didn't reduce falls (Shorr 2012). We don't claim to prevent falls. We target the **long lie**:
   nobody knows she's on the floor. Real-time detection cut the share of fallers who were on the floor
   for 1h+ from 31% to 0 (SafelyYou 2021, but with cameras). We do it without a camera.
2. **"Why voice first, not an instant alert?"** False alarms wreck telecare: carers stop taking
   notifications seriously and switch features off. A wearable fall detector logged 83 false alarms
   out of 84. Checking in with her first filters false alarms before anyone's phone buzzes.
3. **"Why not a camera or a wearable?"** Cameras are consistently the *least* accepted monitoring
   tech for older adults, and pendants aren't used when it counts (in 37 of 38 long lies the faller
   didn't use their alarm). Activity sensors are more acceptable than cameras.
4. **"Does the path light matter?"** Lighting the path improved gait in older adults at high fall
   risk, and an automatic guiding light reduced fear of falling and improved sleep. A fall
   reduction is promising but **not proven**, so say "safer walking", not "prevents falls".
5. **"Can a pillow really tell she's gone?"** Bed sensors detect bed exits with roughly 90%+
   sensitivity and specificity in studies; combining sensors beats any one sensor. We fuse IMU +
   head-warmth temperature + a floor ultrasonic for the same reason.

## Landmine: bed alarms in hospitals

| Finding | Source | Strength |
|---|---|---|
| Pair-matched cluster RCT, 16 hospital units, 18 months: bed alarm use rose ~36-fold with **no significant effect on falls** or fall injuries | [Shorr et al., Ann Intern Med 2012](https://pmc.ncbi.nlm.nih.gov/articles/PMC3549269/) | strong |
| Cochrane review (2018) rated the hospital evidence on bed/chair sensor alarms "very low quality" (reported secondhand) | [summary, Safe-Life 2026](https://safelife.com.au/do-bed-alarms-prevent-falls) | weak (secondary) |

**How to answer:** hospital alarms aim to get a nurse there *before* a fall, which they can't do in
time. Ours works at home, where nobody's there at all. The goal is to cut **time on the floor after
a fall**, plus a light so the walk is safer. Different outcome, different setting.

## Long lies: real-time detection shortens them

| Finding | Source | Strength |
|---|---|---|
| AI video monitoring in 6 memory-care homes (66 residents, 436 falls): fallers on the ground 1h+ went **31% → 0%**; time on the ground −29.6 min | [JMIR 2021, e17551](https://www.jmir.org/2021/6/e17551/) | medium (observational, care homes, cameras) |
| Over-90s cohort: in 97% of long lies (37/38) the person didn't use their installed alarm | [Fleming & Brayne, BMJ 2008](https://www.bmj.com/content/337/bmj.a2227) | strong |
| Long lies predict serious injury, hospital admission and moves into long-term care | [systematic review, Int Emerg Nurs 2022](https://www.sciencedirect.com/science/article/pii/S1755599X22000052) | medium |

## False alarms: why we check in first

| Finding | Source | Strength |
|---|---|---|
| Informal carers using telecare: with frequent false alarms, some **stopped taking push notifications seriously** and turned features off | [Geriatrics (MDPI) 2022, qualitative, 22 carers](https://www.mdpi.com/2308-3417/7/5/86) | medium |
| Wearable fall detector, community-dwelling older adults: **83 of 84 alarms were false** | [PMC4662041](https://pmc.ncbi.nlm.nih.gov/articles/PMC4662041/) | weak (pilot) |
| Pressure-sensor fall systems: false-alarm rates range from negligible to >40%; alarm fatigue is documented | [Medicina (MDPI) 2025, systematic review](https://www.mdpi.com/1648-9144/61/11/1926) | medium |
| Dual-sensor bed-exit alarms (pressure + infrared) were more accurate and gave fewer false alarms than pressure alone, but didn't eliminate them | [Capezuti et al. 2009, PMC2744312](https://pmc.ncbi.nlm.nih.gov/articles/PMC2744312/) | medium |

## Acceptance: no camera, nothing to wear

| Finding | Source | Strength |
|---|---|---|
| Scoping review, 34 studies: activity sensors were more acceptable than cameras, with less privacy concern | [Ageing & Society 2026](https://www.cambridge.org/core/journals/ageing-and-society/article/older-adults-privacy-perceptions-of-passive-inhome-monitoring-technologies-a-comprehensive-scoping-review/165F654FB5275B0DD075FD0A4C174A03) | medium |
| Ambient sensors were more accepted than wearables (Pais et al., within a systematic review) | [JMIR Aging 2024](https://aging.jmir.org/2024/1/e57320/) | medium |
| Smart-home studies 50+: motion/environmental sensors were the most accepted; smart speakers and cameras less so; 87% of studies discussed privacy concerns | [JMIR Aging 2024 scoping review, 15 studies](https://www.sciencedirect.com/org/science/article/pii/S2291522224000330) | medium |
| **Counterpoint:** Swiss survey (n=1,211) found wearables *more* accepted (80%) than home sensors (~60%) and cameras (~35%) | [PubMed 41543981, 2026](https://pubmed.ncbi.nlm.nih.gov/41543981) | medium |

**Honest line:** acceptance of wearables vs sensors is mixed in surveys, but *actual use* of
wearables at the moment of a fall is poor (BMJ 2008; 18% always-wear in persona-evidence.md), and
cameras are the least accepted everywhere. Voice is a mild privacy concern too, so the design
stores no raw audio.

## Voice for older adults living alone

| Finding | Source | Strength |
|---|---|---|
| Systematic review, 13 studies: 84.6% reported reduced loneliness with voice assistants; small, mostly quasi-experimental studies | [Disabil Rehabil Assist Technol 2024](https://www.tandfonline.com/doi/abs/10.1080/17483107.2024.2397030) | medium |
| Scoping review: conversational agents had more benefits than challenges for older adults (ease of use, companionship); challenges were learning and privacy | [PubMed 35852588, 2022](https://pubmed.ncbi.nlm.nih.gov/35852588) | medium |
| Older adults 75+ living alone given Alexa: loneliness fell over 4 weeks | [Yan et al., IJERPH 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC10815345) | weak (n=15) |
| Low-income older adults living alone with AI speakers: one participant said a mood light kept them from falling on dark bathroom trips | [Kim & Kim, SAGE Open 2024, qualitative n=18](https://journals.sagepub.com/doi/10.1177/21582440241301022) | weak (a quote, but a good one) |

## Path lighting at night

| Finding | Source | Strength |
|---|---|---|
| Night lights plus pathway cues improved gait speed and reduced step variability vs night lights alone, in older adults at high fall risk | [Figueiro et al., BMC Geriatr 2011](https://pmc.ncbi.nlm.nih.gov/articles/PMC3176147) | medium (lab, n=24) |
| Lighting that defines horizontal/vertical cues improved balance (weight transfer time) | [Figueiro et al., Age Ageing 2012](https://academic.oup.com/ageing/article/41/3/392/31467) | medium |
| Automatic motion-activated guiding light (bed → bathroom) **reduced fear of falling and improved sleep quality** in community-dwelling older people; too few falls to test fall rate | [PMC7949218 (Gight)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7949218/) | medium |
| Assisted living with dementia, randomized crossover: night lighting gave 34% fewer falls, **not significant** (IDR 0.66, 95% CI 0.35–1.22) | [PubMed 39182511](https://pubmed.ncbi.nlm.nih.gov/39182511) | medium (feasibility) |

## Detection accuracy: can it tell she's gone?

| Finding | Source | Strength |
|---|---|---|
| Pressure sensors + an IMU detected "sitting on the edge, about to exit" with 96.6% accuracy (intention to exit: 74.4%) | [Sensors 2022, PMC9223068](https://pmc.ncbi.nlm.nih.gov/articles/PMC9223068) | weak (prototype) |
| Wireless bed monitor: bed exit sensitivity 90.4%, specificity 93.8% | [Int J Med Inform 2011](https://www.sciencedirect.com/science/article/abs/pii/S1386505610001784) | medium |
| Under-mattress sensor agreed closely with wrist actigraphy on bed entry/exit times at home | [Nat Sci Sleep 2021 (Emfit)](https://www.dovepress.com/emfit-bed-sensor-activity-shows-strong-agreement-with-wrist-actigraphy-peer-reviewed-fulltext-article-NSS) | medium |
| Under-mattress sensor validated for bed occupancy at home and in the lab with 35 older adults; used across 4M+ nights of dementia home monitoring | [Soreq et al., Alzheimer's & Dementia 2022](https://openresearch.surrey.ac.uk/esploro/outputs/journalArticle/Monitoring-abnormal-nocturnal-behaviour-in-the/99783381702346) | medium |

## Not found (don't claim these)

- No trial showing home bed-exit alerts to **family** reduce harm. Family members responding to
  telecare alerts is established practice in England (Steils 2021, below), but there's no outcome trial.
- No study of pillow sensors for **bed exit**. Pillows with sensors exist for sleep posture, head
  movement and vital signs (Jun & Hong 2025, BCGNet 2026, below), so the location is credible; bed
  exit from a pillow is still ours.
- Voice check-ins reducing false alarms: only **simulated** evidence (Tîrziu 2025, below, 200 staged
  videos with a camera). No real-world telecare trial. Say "early evidence", not "proven".

## EBSCO additions (BPP University access)

Searched Fri 23 Oct 2026 via BPP University's EBSCO Discovery Service (Keanu's institution).
Abstracts read in full; numbers come from the abstracts.

**Q&A lines this adds:**
- "Is night really riskier?" Yes: per hour of activity, the risk of falling at home between 1am and
  6am was almost **8× higher** than in the morning (community-dwelling 65+, 501 falls).
- "Isn't 'check in by voice before alerting' just your guess?" Others have built it: a fall-detection
  system that asks the person by voice first, then alerts family, had **fewer false positives** in
  testing. Theirs needs a camera; ours doesn't.
- "Can a pillow really sense anything?" An under-pillow sensor model trained on ~596,000 hours of
  sleep data estimated sleep apnea severity at r > 0.95 against lab sleep studies.

| Finding | Source | Strength |
|---|---|---|
| Community-dwelling 65+ (Netherlands): falls at home track physical activity (r = 0.89), but the risk of falling per hour of activity at **1–6am is almost 8× that of 7am–12pm**; getting out of bed at night is named as a risk | [Wijlhuizen et al., Prev Med 2008, doi:10.1016/j.ypmed.2008.01.017](https://doi.org/10.1016/j.ypmed.2008.01.017) (paywalled) | medium (pooled cohorts, 501 falls) |
| Fall detection + an AI voice assistant that **asks the person first**; no or worrying reply alerts carers or family, processed locally for privacy. Voice confirmation **reduced false positives** | [Tîrziu et al., Future Internet 2025, doi:10.3390/fi17080324](https://doi.org/10.3390/fi17080324) | weak (200 simulated videos, camera-based) |
| Privacy-aware fall detection that uses voice assistants and speakers to check the person's status after a fall before notifying; post-processing removed false positives | [Lupión et al., Internet of Things 2025, doi:10.1016/j.iot.2025.101526](https://doi.org/10.1016/j.iot.2025.101526) (paywalled) | weak (lab) |
| English councils' telecare: **family and unpaid carers commonly act as responders** to alerts from users or monitored devices ("co-workers"), mostly taken for granted | [Steils et al., Ageing & Society 2021, doi:10.1017/S0144686X1900120X](https://doi.org/10.1017/S0144686X1900120X) | medium (national survey + interviews) |
| Rapid response + telecare, north-east England social housing: users felt safer; **family carers said their own health improved because they no longer felt on call all the time**; fewer ambulance call-outs for falls were reported | [Watson et al., Health Soc Care Community 2021, doi:10.1111/hsc.13123](https://doi.org/10.1111/hsc.13123) (paywalled) | weak (qualitative) |
| Hospital delirium unit: a **contactless** 3D-radar bed-exit system was linked to fewer bed-exit falls (11.5 vs 22.6 per 1,000 patient-days) and **fewer warnings** and less nurse time than a contact mat | Eichenbrenner et al., J Am Geriatr Soc 2026 (Jul 31, online), non-randomised controlled trial, 119 patients | medium (hospital, not randomised) |
| Under-pillow ballistocardiography mat: pre-trained on 580,865 h of lab sleep studies, fine-tuned on 15,081 h; 4-class sleep staging F1 0.71–0.82, apnea severity r > 0.95 | [Chen et al., npj Digit Med 2026, doi:10.1038/s41746-026-02885-y](https://doi.org/10.1038/s41746-026-02885-y) | medium (industry-authored, patent disclosed) |
| Sensor-embedded memory-foam pillow: **humidity changed more than temperature** with head movement, so it detected tossing and turning better | Jun & Hong, Bioengineering (Basel) 2025;12(5) | weak (prototype) |

**What this means for the build:**
- The KY-001 temperature probe will be **slow** to show a head on or off (Jun & Hong found
  temperature lags humidity). The DHT11 also measures humidity: putting it inside the pillow
  could give a faster on/off signal.
- Hospital evidence is shifting: older contact mats didn't cut falls (Shorr 2012), but a newer
  contactless system gave fewer warnings and fewer falls (2026). Either way, these are hospitals.

**Possible contradictions:**
- Voice check-in before alerting **has been built before** (Tîrziu 2025, camera-based). Don't claim
  the idea is new. Our angle: no camera, the trigger is "left bed and didn't come back", and alerts
  go to family first.
- By raw count, most falls happen in the active daytime hours (Wijlhuizen). Claim "night is the
  riskiest time per trip out of bed", not "most falls happen at night".
