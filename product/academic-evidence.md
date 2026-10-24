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

## IEEE Xplore additions (BPP University access)

Searched Fri 23–Sat 24 Oct 2026 via BPP University's IEEE Xplore subscription (full text is
available through BPP; numbers below are from the abstracts). All engineering prototypes, mostly
small samples: technical feasibility, not clinical outcomes.

**Q&A: "Can a pillow really tell her head is on it, and how accurate is that?"**
- Yes, and people have built it many ways: pressure buttons, strain threads, piezo + IMU, and
  **temperature + humidity sensors in a pillow classified sleep posture at ~95%** (ICAIIC 2024).
  We use the cheapest version of that idea: one humidity sensor + one temperature probe + an IMU.
- Bed-exit detection with low-cost sensors is a solved engineering problem in the lab: an
  ultrasonic + IR + accelerometer system hit **97.7% sensitivity / 93.8% precision with 11.4 s early
  warning** on ten older adults; a thermopile system caught **100% of bed exits at 1.9% false alarms**
  over months in a nursing home. Our contribution is not the detector; it's what happens next.
- The bedside light we turn on has a published twin: an Arduino LDR + PIR side table that fades in
  low indirect light on foot movement at night, holds 5 min, dims to 10%, then off (ICISS 2026).

| Finding | Source | Strength |
|---|---|---|
| 7 temperature + humidity sensors on a pillow; CNN classified sleep posture with ~95% accuracy; T/H "identify physical changes in the subject" that pressure misses | [Monitoring Sleep Posture Based on Temperature and Humidity Sensor, ICAIIC 2024, 10.1109/ICAIIC60209.2024.10463422](https://doi.org/10.1109/ICAIIC60209.2024.10463422) | weak (conference, small) |
| Low-cost pillow with piezo sensor + IMU measured heart rate, respiration and **head position**; cosine similarity > 0.99 vs ECG | [Pillow-Type Sleep Monitor, ICCE-Taiwan 2026, 10.1109/ICCE-Taiwan71481.2026.11652538](https://doi.org/10.1109/ICCE-Taiwan71481.2026.11652538) | weak (conference) |
| FBG pressure buttons in a pillow tracked head position and movement in real time, plus respiratory rate | [SleepSense, IEEE Sensors J 2023, 10.1109/JSEN.2023.3295114](https://doi.org/10.1109/JSEN.2023.3295114) | medium (journal, 41 citations) |
| Strain-sensing threads sewn into a memory-foam pillow tracked head motion; linear over 50 g–5 kg | [IEEE Sensors 2022, 10.1109/SENSORS52175.2022.9967140](https://doi.org/10.1109/SENSORS52175.2022.9967140) | weak (preliminary) |
| Tactile-sensor pillow ("uSkin") gave movement, sleep duration, respiratory rate and position; **elderly users rated it user-friendly**, accuracy comparable to commercial devices | [uSkin Pillow, CyberSciTech 2024, 10.1109/CyberSciTech64112.2024.00061](https://doi.org/10.1109/CyberSciTech64112.2024.00061) | weak (conference) |
| ESP32 smart pillow with temperature, pressure and sound sensors fused to detect sleep disruption | [Zenith Zzz Guard, ICCNCT 2026, 10.1109/ICCNCT68477.2026.11590823](https://doi.org/10.1109/ICCNCT68477.2026.11590823) | weak (conference; close to our stack) |
| Ultrasonic (in bed) + IR (crossing the bed edge) + accelerometer, SVM: bed-exit **sensitivity 97.7%, precision 93.8%, 11.4 s average lead time**, 10 older adults | [IEEE Sensors Letters 2024, 10.1109/LSENS.2023.3336647](https://doi.org/10.1109/LSENS.2023.3336647) | medium (letter, 10 participants) |
| 12×16 thermopile behind the bed + pseudo-Siamese CNN: **100% detection, 1.9% false alarms**; 222 and 98 real bed exits over 60 and 41 nights with two nursing-home residents | [IEEE Sensors J 2025, 10.1109/JSEN.2025.3576801](https://doi.org/10.1109/JSEN.2025.3576801) | medium (journal, n=2 long-term) |
| Capacitive printed electrode under the sheet: detected bed exit **3.5 s earlier than a commercial mat**, no false detections across 95 posture changes and 50 exits | [BSN 2024, 10.1109/BSN63547.2024.10780504](https://doi.org/10.1109/BSN63547.2024.10780504) | weak (5 simulated participants) |
| IR + pressure sensors with a **finite state machine** detect bed exit and falls for older adults living alone | [ICARM 2016, 10.1109/ICARM.2016.7606895](https://doi.org/10.1109/ICARM.2016.7606895) | weak (conference) |
| Accelerometer-only bed occupancy (phone on bed, 249 h, 7 patients), LSTM: AUC 0.94; "brief activity bursts interspersed with long periods of little or no activity, even when the bed is occupied" | [IEEE Access 2023, 10.1109/ACCESS.2023.3261557](https://doi.org/10.1109/ACCESS.2023.3261557) | medium |
| ICASSP 2025 grand challenge on accelerometer-only person-in-bed detection, focused on low-cost, low-latency streaming detection | [ICASSP 2025, 10.1109/ICASSP49660.2025.10887832](https://doi.org/10.1109/ICASSP49660.2025.10887832) | medium (benchmark) |
| Environmental sensors (CO₂, VOC, temperature, humidity) fused for room occupancy: 81.1% accuracy; detect non-moving occupants that motion sensors miss | [IEEE IoT J 2018, 10.1109/JIOT.2017.2752134](https://doi.org/10.1109/JIOT.2017.2752134) | medium |
| Arduino LDR + PIR smart side table: low indirect light fades in on foot movement at night, 5 min navigation light, dims to 10% for 30 min, then off; motivated by nocturia falls | [ICISS 2026, 10.1109/ICISS71466.2026.11715027](https://doi.org/10.1109/ICISS71466.2026.11715027) | weak (prototype, no users) |
| Review: bed-fall systems split into detection vs prediction, classified by sensor type | [IEEE Sensors J 2021, 10.1109/JSEN.2020.3037711](https://doi.org/10.1109/JSEN.2020.3037711) | medium (review) |
| LLM voice framework for older adults living alone: medication reminders, conversation, kept context | [ICCE 2025, 10.1109/ICCE63647.2025.10930020](https://doi.org/10.1109/ICCE63647.2025.10930020) | weak (framework, no trial) |
| Privacy-preserving AAL architecture: on-premises local VLMs, IoT, robots, natural-language intents turned into executable task graphs | [CogAAL, MetroLivEnv 2026, 10.1109/MetroLivEnv70468.2026.11659911](https://doi.org/10.1109/MetroLivEnv70468.2026.11659911) | weak (architecture) |

### Build implications (firmware)

- **Accelerometer stillness is not absence.** Occupied beds show long stretches of near-zero motion
  (IEEE Access 2023), so `head_on` must come from warmth/humidity, not from the MPU6050; use the IMU
  for restlessness and the moment of getting up. That's how `pillow.ino` already splits it.
- **Fuse, and detect the transition.** Every accurate bed-exit system combines two or more sensors
  (ultrasonic + IR + accel; IR + pressure) and models the exit as a sequence: a state machine
  (ICARM 2016) or classifier on the transition. Our server-side state machine
  (`lay_down` → `bed_exit` → `no_return`) matches that design; keep thresholds in code, not the LLM.
- **Ultrasonic placement:** the 97.7% system used ultrasonic to sense the person *in bed* and IR at
  the bed edge. Our floor-pointing ultrasonic (`ROOM_NEAR_CM`) is the cheaper "standing beside the
  bed" signal; aim it along the side the resident gets out on.
- **Path light behaviour to copy:** fade in, low and indirect, ~5 min, then dim to ~10% (ICISS 2026).
- **Humidity is a real signal** in a pillow (posture at ~95% with T/H), supporting the DHT11 head
  detection in PR #5; tune `HEAD_DELTA_RH` on a real night.

### Contradictions and caveats

- Several groups already sell or publish smart pillows and bed-exit systems with higher accuracy
  than ours will have. Don't pitch the sensing as novel; pitch the **agent + voice check-in +
  family routing**, with sensing "in line with published designs".
- LLM-based elder-care systems exist (ICCE 2025, CogAAL 2026), all early-stage with no outcome data.
  "Agentic" alone isn't a differentiator; the night-time, no-camera, act-then-ask-then-escalate loop is.
- Still no paper found on a pillow detecting **bed exit** specifically; pillow work is about posture,
  vitals and sleep. That gap remains ours.
