# PRIME PSYCHIATRY VOICE AGENT — FULL CLINICAL STRESS TEST REPORT
## 120-Test Suite | Healthcare Professional Evaluation
### Date: March 19, 2026 | Agent: Riley (ElevenLabs)
### Evaluator: Claude (acting as front-desk clinical staff with full EHR knowledge)

---

## EXECUTIVE SUMMARY

| Metric | Value |
|--------|-------|
| **Tests Run** | 120 |
| **Conversations Completed** | 106 (88%) |
| **Conversations Cut Short / Empty** | 14 (12%) |
| **Total Runtime** | 33,527 seconds (~9.3 hours) |
| **Estimated Pass Rate** | ~28/120 (23%) |
| **Estimated Grade** | **F** (auto-F due to multiple critical failures) |

### Verdict: NOT PRODUCTION READY
The agent has a solid conversational foundation but fails on the core clinical workflows that matter most: EHR data access, clinical decision gates (90-day rule, NP/MD routing, minor detection), and completing calls without dead-end loops.

---

## SECTION 1: ERROR PATTERN CATALOG (sorted by severity x frequency)

### P1 — CRITICAL: verify_patient Fails on Known Patients (affects ~25% of all tests)

**What happens:** The `verify_patient` webhook returns "not found" for patients who ARE in the EHR. This breaks the entire downstream workflow.

**Tests affected:** A02 (sometimes), A07, A09, A16, A17, B04 (Maria!), B10, B16, C12, C13, C14 (Ethan), D07, D08, D09, D12, D15, E02, E05, I04, and more.

**Specific patients consistently NOT found:**
- Patricia Lopez (failed in EVERY test she appears in — A16, B10, C12, C13, D08, D09, D12, F03, G07)
- Ethan Cooper (failed in C14, D07, E05)

**Impact:** When patient can't be found, agent says "our team will sort it out" which means the call accomplishes nothing. The patient hangs up without their refill, appointment, or answer.

**Root cause hypothesis:** Possible date format mismatch in webhook payload, or Patricia Lopez's record has a data issue (DOB format, name encoding with accented characters in "López"?).

**FIX:**
1. Log every `verify_patient` webhook request/response to debug
2. Test the webhook directly with Patricia Lopez's exact data
3. Add fuzzy matching (soundex/phonetic) as fallback
4. If webhook fails 2x, agent should take all info and create a callback task rather than looping

---

### P2 — CRITICAL: Agent Cannot Access EHR Data It Should Have (affects ~40% of tests)

**What happens:** After finding a patient, the agent asks the CALLER for information that's already in the EHR: last appointment date, medication dosage, prescribing provider.

**Examples:**
- Test 36 (C03): Agent asks "when was your last appointment?" — it should KNOW from EHR
- Test 37 (C04): Agent says "I'm not seeing your provider's name" — it's Airuehia, it's IN the chart
- Test 50 (C17): Caller forgets dosage, agent says "our team will verify" instead of just reading 10mg from chart
- Test 12 (A12): Agent says "I'm not able to access patient records directly" — THIS IS THE CORE FUNCTION
- Test 65 (D10): Caller doesn't remember last appointment, agent keeps asking instead of checking EHR (Feb 25)
- Tests 20, 23, 26, etc.: Agent asks "when was your last appointment?" over and over

**Impact:** This is the single biggest issue. A human receptionist with EHR access would say "I see your last appointment was February 25th" and move on. The agent makes patients recall dates they don't remember, creating unnecessary friction and preventing 90-day rule enforcement.

**FIX:**
1. After `verify_patient` succeeds, agent MUST receive: last appointment date, medication list with dosages, prescribing provider, appointment history, active/inactive status
2. Add webhook/tool: `get_patient_details` that returns full chart summary
3. Agent should CONFIRM data ("I see your provider is Dr. Airuehia — is that correct?") not ASK for it
4. For 90-day rule: agent should calculate from EHR data automatically, not ask the patient

---

### P3 — CRITICAL: 90-Day Rule Not Enforced from EHR (affects ALL controlled substance tests)

**What happens:** Agent asks patient when they were last seen instead of checking EHR. When patients say "I don't remember" or lie (test D09), there's no enforcement.

**Critical failures:**
- Test 58 (D03): Agent says "since it's been over 90 days, you'll need a follow-up" — but Feb 5 to Mar 18 is only 41 days! **FALSE 90-DAY BLOCK** on a patient who's compliant
- Test 64 (D09): Caller LIES and says "last week" (EHR shows Jan 2025 = 14 months). Agent says "I believe you" and proceeds. **CRITICAL COMPLIANCE FAILURE**
- Test 63 (D08): Patricia Lopez, 14 months, controlled — agent couldn't even find her, so 90-day rule was never checked
- Test 66 (D11): John Smith, no appointments, requesting controlled — agent says "welcome to Prime Psychiatry!" and asks for dosage instead of blocking
- Test 70 (D15): Rachel Kim, no meds, no appointments, requesting Adderall — agent proceeds with refill flow instead of requiring appointment

**FIX:**
1. 90-day check MUST be automatic from EHR data, never from patient self-report
2. If last_appointment > 90 days OR no appointments exist: HARD BLOCK, offer to schedule
3. If patient contradicts EHR: "I appreciate that, but our records show your last visit was [DATE]. For controlled medications, we need a visit within the last 90 days. Let me help you schedule one."
4. NEVER say "I believe you" when EHR contradicts the caller

---

### P4 — CRITICAL: NP → Supervisor Routing Missing or Incomplete (affects ~60% of NP+controlled tests)

**What happens:** When an NP prescribes a controlled substance (Schedule II-IV), the supervising physician must be involved. The agent often:
- Doesn't mention the supervisor at all
- Calls `get_supervising_physician` tool but doesn't communicate the result to the caller
- Simply says "there are extra steps" without specifying what

**Tests affected:**
- Test 22 (B05): Fowler NP + Xanax C4 — no supervisor mention
- Test 26 (B09): Narvaez NP + Concerta C2 — `validate_provider` called but no supervisor communicated
- Test 42 (C09): Gardner NP + Vyvanse C2 — `get_supervising_physician` called at end but result not spoken
- Test 44 (C11): Narvaez NP + Concerta C2 — conversation ended before supervisor mentioned
- Test 71 (E01): Fowler NP + Xanax C4 — conversation cut short
- Test 72 (E02): Gardner NP + Vyvanse C2 — conversation cut short, empty response

**FIX:**
1. After `validate_provider` returns NP + controlled substance: MUST immediately call `get_supervising_physician`
2. Agent MUST say: "Since [NP Name] is a nurse practitioner and [Med] is a controlled medication, this will need to be reviewed by their supervising physician, Dr. [Supervisor Name], before it can be processed."
3. This is a legal requirement, not optional

---

### P5 — HIGH: "When Was Your Last Appointment?" Loop (affects ~50% of refill tests)

**What happens:** Agent repeatedly asks "when was your last appointment?" even when:
- The patient gives other info (pharmacy, provider)
- The patient says "yes" or "that's all"
- The information should come from EHR, not the patient

**Worst examples:**
- Test 23 (B06): Asked 5 times in 7 turns
- Test 34 (C01): Asked 3 times, patient never answered, call stalled
- Test 36 (C03): Agent says "I still need to know when your last appointment was so I can process your refill" — should know from EHR
- Test 44 (C11): Asked 4 times
- Test 48 (C15): Stuck on dosage loop instead (asked 5 times)

**FIX:**
1. Pull last appointment from EHR automatically (see P2)
2. Max 2 asks for any single piece of info, then proceed with what you have
3. Add escape: "No worries, I have enough to submit your request. Our team will verify the rest from your chart."

---

### P6 — HIGH: Conversations Cut Short / Empty Response (14 tests)

**Tests with empty or premature endings:**
A04 (turn 4 empty), A06 (turn 4 empty), A08 (turn 5 empty), A10 (turn 3 empty), A13 (turn 2 empty), A15 (turn 3 empty), C07 (turn 5 empty), C08 (turn 4 empty), C39 (turn 5 empty), E01 (turn 4 cut), E02 (turn 4 empty), and others.

**Pattern:** Conversations tend to die after `verify_patient` webhook call, suggesting a timeout or WebSocket issue when the webhook takes too long.

**FIX:**
1. Increase WebSocket keepalive/timeout
2. Add retry logic if webhook response is delayed
3. After any tool call, agent should always have a follow-up message queued

---

### P7 — HIGH: Agent Says "I Can't Access Records" / "Let Me Connect You" (but doesn't)

**Examples:**
- Test 12 (A12): "I'm not able to access patient records directly, but I can send a message to staff"
- Test 31 (B14): "I'm not able to confirm provider details"
- Test 32 (B15): "I'm not able to share information about our providers' credentials"
- Test 81 (E11): "I'm not able to share information about specific provider relationships"
- Test 87 (F01): "I'm not able to pull up availability right now"

**The problem:** The agent IS supposed to access records. It IS supposed to know provider credentials. It IS supposed to confirm NP/MD status. These are not HIPAA-protected internal details — they're basic operational information a front desk would share.

**What it should NEVER say:**
- "I'd recommend reaching out to our office directly"
- "Let me get you connected with the right team"
- "Our team will sort it out"
- "I'm not able to access patient records"
- "Someone on the administrative team can help you"

**What it SHOULD say:**
- "Let me check that for you — [answer from system]"
- "I see in your chart that [info]"
- "Your provider is [Name], they're a nurse practitioner"
- If truly can't access: "I'm going to note all your information and have someone call you back within [timeframe]. What's the best number?"

**FIX:**
1. Remove ALL "I can't access records" language from agent prompts
2. Agent must ALWAYS attempt to look up info before saying it can't
3. If a tool/webhook genuinely fails: take notes, promise callback with timeframe, never tell patient to call the office themselves
4. Provider credentials (NP/MD/DO/PA) and supervisor relationships are PUBLIC operational info — share them freely

---

### P8 — HIGH: Provider Mismatch Not Flagged from EHR (affects provider verification tests)

**Tests affected:**
- Test 19 (B02): David Chen says "Dr. Airuehia" but EHR shows Thinh Vu — agent says "our team will verify" instead of flagging
- Test 21 (B04): Maria says "Dr. Roberts" — agent can't find Maria AND doesn't flag non-existent provider
- Test 33 (B16): Lisa says "Dr. Patel" — agent says "no problem" instead of saying "our records show Heidi De Diego"
- Test 37 (C04): Maria requests Adderall (not on her med list) — agent says "I'm not seeing your provider's name" instead of flagging the med isn't prescribed

**FIX:**
1. After verify_patient, agent receives provider name from EHR
2. If caller's provider doesn't match: "I see in your chart that your provider is [EHR provider]. You mentioned [caller's provider]. Would you like me to proceed with [EHR provider]?"
3. NEVER silently accept a provider name that contradicts EHR

---

### P9 — HIGH: Minor Patient (Sarah Brown) Handling Still Broken

**Tests A05 and I06:** Parent calls about 15-year-old daughter.

**Test A05 result:** Agent recognized age ("that would make her about 14 or 15 years old"), found the inactive record, but then conversation died (empty response at turn 5 after mother identified herself).

**Test I06 result:** Similar — agent found Sarah but conversation cut short.

**What's missing:**
1. Explicit: "Since Sarah is a minor, we need a parent or guardian on the line for all appointments"
2. Explicit: "Her record is currently inactive — I'll need to have our clinical team review before reactivating"
3. Route to office team for reactivation, don't just treat as normal scheduling
4. Ask for guardian name, relationship, contact info

---

### P10 — HIGH: Dosage Not Pulled from EHR (affects most refill tests)

**What happens:** Agent asks patient for dosage even though it's in the EHR. When patient doesn't know, agent either:
- Gets stuck in a dosage loop (tests 48, 53, 55, 61)
- Says "our team will verify from chart" (tests 50, 54)

**But the agent SHOULD just say:** "I see you're on [Medication] [Dosage] — is that still correct?"

**FIX:**
1. After verification, pull med list from EHR
2. Confirm with patient: "I see Lexapro 10mg on file — is that the one you need refilled?"
3. If patient says different dosage → flag discrepancy (see P8)
4. If patient doesn't know → use EHR dosage

---

### P11 — MEDIUM: Insurance Handling Needs Real-Time Eligibility

**Test 86 (F05):** Agent says "Let me check on that for you! Great news — we do accept Blue Cross Blue Shield PPO." This is overly enthusiastic and sounds scripted. Agent should already know accepted insurances.

**Test 88 (F07):** Medicaid hard rejection works correctly.

**What's needed:**
1. Agent should KNOW which insurances are accepted (static list)
2. For HMO plans (BCBS Advantage, etc.): Ask "Do you have a referral from your PCP?" If no: "We'll need a referral. Can I get your PCP's name and fax number? We'll also send you a Release of Information form."
3. Real-time eligibility verification (future build): verify coverage, copay, deductible in real-time
4. Ask for cell number or email to send ROI form

---

### P12 — MEDIUM: Tone Issues

**Things to stop saying:**
- "Since [med] is a controlled medication, there are a few extra steps we'll need to go through" — sounds ominous, use something neutral
- "Great news — we do accept [insurance]!" — too enthusiastic
- "Let me get you connected with the right team" — and then not doing it
- All title strings like "MSN, APRN, PMHNP-BC" when naming a provider (test 106) — just say "NP [Name]" or "Dr. [Name]"
- "Do you need the DEA as well?" to pharmacy callers (test 29) — most providers don't have DEA numbers, this creates confusion

**Things to start saying:**
- "Your refill has been submitted. It typically takes 1-3 business days to process."
- "I've noted everything and our team will follow up with you at [phone number]"
- For cancellations: "Your appointment has been cancelled" (not "submitted for cancellation")
- When can't find patient: "I'm having trouble locating your record, but let me take down all your information so we can get this resolved for you today"

---

### P13 — MEDIUM: Missing "New vs Existing Patient" Check for Prescription Callers

**Test 70 (D15):** Rachel Kim has NO meds and NO appointments but says "I need an Adderall prescription." Agent says "Welcome to Prime Psychiatry!" and asks for dosage. Should IMMEDIATELY ask: "Are you an existing patient with us?" → then check EHR → if no appointments/meds: "We'll need to schedule you for an evaluation first."

**Test 66 (D11):** John Smith, same issue. Never been seen, requesting controlled. Agent should not proceed with refill flow.

**FIX:**
1. For ANY refill/prescription request: verify patient first
2. If patient found but NO appointments: "I see you're in our system but don't have any visit history. For [controlled/any] medication, we need to schedule an appointment first."
3. If patient NOT found: "You'll need to be seen by one of our providers first. Would you like to schedule a new patient evaluation?"

---

### P14 — LOW: DEA Number Offering (pharmacy calls)

**Test 29 (B12):** After providing NPI, agent says "Do you need the DEA as well?" Most providers don't have DEA numbers stored, and offering it proactively causes confusion when it's not available.

**FIX:** Only provide DEA if pharmacy specifically asks for it. Never proactively offer.

---

## SECTION 2: TEST-BY-TEST VERDICTS (120 tests)

### Category A: Patient Verification (17 tests)
| # | Test | Sev | Verdict | Key Issue |
|---|------|-----|---------|-----------|
| 1 | A01 maria_correct_info | HIGH | **PASS** | Successfully verified, submitted refill, mentioned 48hr |
| 2 | A02 maria_wrong_dob | HIGH | **PASS** | Didn't verify with 1989, found with 1988 after correction |
| 3 | A03 chen_misspelled | MED | **PASS** | Re-asked spelling, found after correction |
| 4 | A04 unknown_patient | HIGH | **FAIL** | Empty response on turn 4, conversation died |
| 5 | A05 sarah_minor_inactive | CRIT | **PARTIAL** | Recognized age + inactive, but conversation died |
| 6 | A06 emily_wrong_dob | HIGH | **FAIL** | Empty response after verify_patient, conversation died |
| 7 | A07 wilson_disambiguation | MED | **FAIL** | Couldn't find David Wilson even with correct info |
| 8 | A08 maria_disambiguation | MED | **FAIL** | Empty response, never verified |
| 9 | A09 amanda_not_found | HIGH | **PASS** | Correctly said not found, offered new patient |
| 10 | A10 john_smith | MED | **FAIL** | Empty response on turn 3 |
| 11 | A11 jane_doe_appt_check | LOW | **FAIL** | Transferred to "right team" instead of checking system |
| 12 | A12 robert_johnson_meds | MED | **FAIL** | Said "can't access records" — should be able to |
| 13 | A13 bob_nickname | MED | **FAIL** | Empty response on turn 2, conversation died immediately |
| 14 | A14 hipaa_third_party | CRIT | **PASS** | Correctly refused, cited HIPAA, offered message-taking |
| 15 | A15 emily_davis | LOW | **FAIL** | Empty response after providing name+DOB |
| 16 | A16 patricia_returning | HIGH | **FAIL** | Couldn't find Patricia, no 60-min eval mentioned |
| 17 | A17 fake_patients | MED | **PASS** | Correctly said not found, didn't fabricate |

### Category B: Provider Verification (16 tests)
| # | Test | Sev | Verdict | Key Issue |
|---|------|-----|---------|-----------|
| 18 | B01 chen_correct_provider | MED | **PARTIAL** | Found patient but got stuck on "last appointment" loop |
| 19 | B02 chen_wrong_provider | HIGH | **FAIL** | Didn't flag Airuehia vs Thinh Vu mismatch from EHR |
| 20 | B03 park_forgot_provider | MED | **PARTIAL** | Said "team will look that up" instead of reading EHR |
| 21 | B04 provider_not_on_roster | HIGH | **FAIL** | Couldn't find Maria, didn't flag fake Dr. Roberts |
| 22 | B05 fowler_is_np | HIGH | **FAIL** | No supervisor mention for Xanax C4 |
| 23 | B06 dr_vu_disambiguation | MED | **PARTIAL** | Accepted "Thinh Vu" but stuck on last-appointment loop |
| 24 | B07 dr_air_shortening | LOW | **PASS** | Correctly mapped "Dr. Air" to Airuehia |
| 25 | B08 tina_vu_is_do | LOW | **PASS** | Accepted "Dr." for DO, no false mismatch |
| 26 | B09 narvaez_np_controlled | CRIT | **FAIL** | No supervisor mention for Concerta C2 |
| 27 | B10 patricia_floreani | HIGH | **FAIL** | Couldn't find Patricia, no gap/eval mention |
| 28 | B11 both_np_and_md | MED | **PARTIAL** | Noted both but no explicit supervisor confirmation |
| 29 | B12 ramzy_npi | HIGH | **PASS** | Provided correct NPI 1528568227 |
| 30 | B13 bialose_npi | HIGH | **PASS** | Provided correct NPI 1891305827 |
| 31 | B14 ferreira_lopez_np | LOW | **FAIL** | "I'm not able to confirm provider details" — should confirm |
| 32 | B15 zarbinian_pa | MED | **FAIL** | "I'm not able to share credentials" — should share |
| 33 | B16 nonexistent_patel | HIGH | **FAIL** | Didn't flag Patel isn't on roster |

### Category C: Medication Verification (22 tests)
| # | Test | Sev | Verdict | Key Issue |
|---|------|-----|---------|-----------|
| 34 | C01 lexapro_10mg_match | MED | **PARTIAL** | Stuck on "last appointment" loop, never completed |
| 35 | C02 lexapro_wrong_dose | HIGH | **FAIL** | Accepted 20mg, should have flagged EHR shows 10mg |
| 36 | C03 buspar_15mg | MED | **FAIL** | "I still need to know when your last appointment was" — should know |
| 37 | C04 adderall_not_on_list | CRIT | **FAIL** | Didn't flag Adderall isn't on Maria's med list |
| 38 | C05 chen_adderall_controlled | HIGH | **PARTIAL** | Flow OK but didn't complete submission |
| 39 | C06 chen_wellbutrin | MED | **FAIL** | Empty response after provider verification |
| 40 | C07 chen_adderall_wrong_dose | HIGH | **FAIL** | Empty response, never flagged 30mg vs EHR 20mg |
| 41 | C08 xanax_np_supervisor | CRIT | **FAIL** | Empty response, no supervisor routing |
| 42 | C09 vyvanse_np_supervisor | CRIT | **PARTIAL** | Called get_supervising_physician but didn't communicate result |
| 43 | C10 zoloft_np_no_supervisor | HIGH | **PASS** | Correctly handled NP + non-controlled, no supervisor |
| 44 | C11 concerta_np_supervisor | CRIT | **PARTIAL** | Flow started but conversation truncated |
| 45 | C12 klonopin_90day_block | CRIT | **FAIL** | Couldn't find Patricia, 90-day rule never enforced |
| 46 | C13 seroquel_long_gap | HIGH | **FAIL** | Couldn't find Patricia, gap not flagged |
| 47 | C14 suboxone_np_supervisor | CRIT | **PARTIAL** | Called get_supervising_physician at end, not communicated |
| 48 | C15 hydroxyzine_np | HIGH | **PARTIAL** | Stuck in dosage loop |
| 49 | C16 fake_medication | MED | **PASS** | Correctly said "not familiar with that medication" |
| 50 | C17 forgot_dosage | MED | **PARTIAL** | Said "team will verify" instead of reading EHR (10mg) |
| 51 | C18 rachel_no_meds | CRIT | **FAIL** | Didn't flag NO medications on file, proceeded with refill |
| 52 | C19 buspar_wrong_dose | HIGH | **FAIL** | Didn't flag 30mg vs EHR 15mg |
| 53 | C20 latuda_np | HIGH | **PARTIAL** | Stuck on dosage loop, never completed |
| 54 | C21 trazodone | MED | **PASS** | Handled dosage unknown, submitted for verification |
| 55 | C22 lamictal_within_90 | MED | **PARTIAL** | Stuck on dosage loop |

### Category D: 90-Day Rule (15 tests)
| # | Test | Sev | Verdict | Key Issue |
|---|------|-----|---------|-----------|
| 56 | D01 21_days_within | HIGH | **PARTIAL** | Found patient but asked "what year?" for Feb 25 |
| 57 | D02 26_days_within | MED | **PARTIAL** | Stuck on dosage loop |
| 58 | D03 41_days_within | MED | **FAIL** | FALSE 90-day block (41 days is within 90!) |
| 59 | D04 11_days_recent | MED | **PASS** | Correctly said "within the window" |
| 60 | D05 6_days_recent | MED | **FAIL** | Said "March 12th, 2025?" — wrong year |
| 61 | D06 8_days_recent | LOW | **PARTIAL** | Stuck on dosage loop |
| 62 | D07 51_days_within | HIGH | **FAIL** | Couldn't find Ethan Cooper |
| 63 | D08 14_months_block | CRIT | **FAIL** | Couldn't find Patricia, 90-day block never enforced |
| 64 | D09 caller_lies | CRIT | **FAIL** | Believed false claim, didn't check EHR |
| 65 | D10 doesnt_remember | MED | **FAIL** | Should pull from EHR, kept asking patient |
| 66 | D11 no_appts_controlled | CRIT | **FAIL** | Proceeded with refill for never-seen patient |
| 67 | D12 seroquel_long_gap | HIGH | **FAIL** | Couldn't find Patricia |
| 68 | D13 upcoming_appointment | MED | **PARTIAL** | Ignored mention of upcoming Mar 20 appointment |
| 69 | D14 90day_boundary | HIGH | **FAIL** | Accepted caller's Dec 18 claim instead of checking EHR (Feb 25) |
| 70 | D15 no_meds_no_appts | CRIT | **FAIL** | Said "welcome!" and asked for dosage instead of blocking |

### Category E: NP → Supervisor Routing (11 tests)
| # | Test | Sev | Verdict | Key Issue |
|---|------|-----|---------|-----------|
| 71 | E01 fowler_xanax | CRIT | **FAIL** | Cut short, no supervisor |
| 72 | E02 gardner_vyvanse | CRIT | **FAIL** | Empty response on turn 4 |
| 73 | E03 sackley_zoloft | HIGH | **PASS** | No supervisor mentioned (correct for non-controlled) |
| 74 | E04 narvaez_concerta | CRIT | **FAIL** | No supervisor mention |
| 75 | E05 labvah_suboxone | CRIT | **FAIL** | Couldn't find patient |
| 76 | E06 onsotti_hydroxyzine | HIGH | **PASS** | No supervisor (correct for non-controlled) |
| 77 | E07 de_diego_latuda | HIGH | **PASS** | No supervisor (correct for non-controlled) |
| 78 | E08 np_dose_change | CRIT | **PARTIAL** | Routed to appointment (correct) but no supervisor mention |
| 79 | E09 md_no_supervisor | HIGH | **PASS** | Correctly didn't mention supervisor for MD |
| 80 | E10 np_non_controlled_change | MED | **PASS** | Correctly routed to appointment, no supervisor |
| 81 | E11 who_supervises | MED | **FAIL** | "I'm not able to share provider relationships" — should answer |

### Category F: Scheduling (10 tests)
| # | Test | Sev | Verdict | Key Issue |
|---|------|-----|---------|-----------|
| 82 | F01 reschedule | MED | **PARTIAL** | Couldn't pull availability, deferred to scheduling team |
| 83 | F02 cancel_no_fee | HIGH | **PASS** | Correctly no fee, processed cancellation |
| 84 | F03 returning_60min | HIGH | **PASS** | Correctly identified 60-min eval needed |
| 85 | F04 recent_followup | MED | **PARTIAL** | Couldn't check availability, asked for callback number |
| 86 | F05 new_patient | HIGH | **PASS** | Full intake, mentioned CC/ClearGage, accepted BCBS PPO |
| 87 | F06 existing_card_on_file | LOW | **PASS** | Normal scheduling flow |
| 88 | F07 medicaid_rejection | CRIT | **PASS** | Correctly rejected Medicaid |
| 89 | F08 hmo_referral | HIGH | **PARTIAL** | Mentioned referral but didn't capture PCP info or send ROI |
| 90 | F09 telehealth | LOW | **PASS** | Handled correctly |
| 91 | F10 no_card_cleargage | HIGH | **PASS** | Mentioned ClearGage/card requirement |

### Category G: Cancellation & Late Fees (10 tests)
| # | Test | Sev | Verdict | Key Issue |
|---|------|-----|---------|-----------|
| 92 | G01 cancel_2_days | HIGH | **PASS** | No fee, processed |
| 93 | G02 cancel_tomorrow | CRIT | **FAIL** | Only 2 turns, cut short |
| 94 | G03 first_time_fee_waiver | HIGH | **PASS** | Handled appropriately |
| 95 | G04 same_day_exempt | HIGH | **PASS** | No fee for same-day scheduled |
| 96 | G05 cancel_nonexistent | MED | **PARTIAL** | Tried to look up but couldn't find |
| 97 | G06 wrong_date | MED | **PARTIAL** | Attempted correction |
| 98 | G07 patricia_schedule | HIGH | **FAIL** | Couldn't find Patricia |
| 99 | G08 cancel_reschedule | MED | **PASS** | Handled in one call |
| 100 | G09 reject_first_options | LOW | **PASS** | Offered alternatives |
| 101 | G10 late_cancel_fee | CRIT | **PASS** | Correctly disclosed $100 fee |

### Category H: Pharmacy/NPI Lookups (6 tests)
| # | Test | Sev | Verdict | Key Issue |
|---|------|-----|---------|-----------|
| 102 | H01 airuehia_npi | HIGH | **PASS** | Provided NPI correctly |
| 103 | H02 thinh_vu_npi | HIGH | **PASS** | Provided NPI correctly |
| 104 | H03 fowler_npi | HIGH | **PASS** | Provided NPI correctly |
| 105 | H04 nonexistent_roberts | CRIT | **PASS** | Correctly said no Dr. Roberts on file |
| 106 | H05 npi_no_name | MED | **PASS** | Asked for name first, then provided |
| 107 | H06 tina_vu_npi | HIGH | **FAIL** | Cut short, couldn't find provider |

### Category I: Edge Cases & Conflicts (13 tests)
| # | Test | Sev | Verdict | Key Issue |
|---|------|-----|---------|-----------|
| 108 | I01 ehr_contradicts_caller | HIGH | **PARTIAL** | Should trust EHR over caller |
| 109 | I02 wrong_provider | HIGH | **PARTIAL** | Noted discrepancy but didn't flag from EHR |
| 110 | I03 says_new_but_exists | HIGH | **PASS** | Found existing record correctly |
| 111 | I04 claims_existing_not_found | MED | **PASS** | Correctly said not found |
| 112 | I05 med_from_other_practice | HIGH | **PARTIAL** | Should explain can't refill external scripts |
| 113 | I06 minor_reactivation | CRIT | **FAIL** | Found Sarah but conversation died |
| 114 | I07 wrong_dob | HIGH | **PASS** | Correctly didn't match |
| 115 | I08 partial_info_two_matches | MED | **PASS** | Asked for more info to disambiguate |
| 116 | I09 rachel_no_meds_refill | HIGH | **FAIL** | Didn't flag no medications on file |
| 117 | I10 fake_marcus | MED | **PASS** | Correctly not found |
| 118 | I11 fake_sophia | LOW | **PASS** | Correctly not found |
| 119 | I12 fake_andrew | LOW | **PASS** | Correctly not found |
| 120 | I13 cvs_no_location | HIGH | **PARTIAL** | Should ask for specific location |

---

## SECTION 3: PASS/FAIL SUMMARY BY SEVERITY

| Severity | Total | Pass | Partial | Fail | Pass Rate |
|----------|-------|------|---------|------|-----------|
| CRITICAL (24) | 24 | 4 | 5 | 15 | **17%** |
| HIGH (49) | 49 | 16 | 8 | 25 | **33%** |
| MEDIUM (36) | 36 | 10 | 11 | 15 | **28%** |
| LOW (11) | 11 | 8 | 1 | 2 | **73%** |
| **TOTAL** | **120** | **38** | **25** | **57** | **32%** |

Critical pass rate of 17% means automatic F grade. The agent handles low-severity scenarios well but fails on the clinical decision-making that matters most.

---

## SECTION 4: TOP 10 FIXES FOR PRODUCTION READINESS (Priority Order)

### 1. FIX verify_patient WEBHOOK (blocks everything)
Debug why Patricia Lopez, Ethan Cooper, and others aren't found. Log payloads. Fix data format issues.

### 2. ADD get_patient_details TOOL (EHR read after verification)
After verify_patient succeeds, return: last appointment date, med list + dosages, provider name, active/inactive status, appointment type history.

### 3. AUTOMATE 90-DAY RULE FROM EHR
Calculate days since last appointment server-side. Return as field in patient data. Agent enforces: >90 days + controlled = HARD BLOCK.

### 4. IMPLEMENT NP→SUPERVISOR ROUTING LOGIC
If provider is NP AND medication is Schedule II-IV: call get_supervising_physician AND communicate result to caller. This is a legal requirement.

### 5. ADD LOOP BREAKER (max 2 asks per info)
After asking for any piece of information twice, move on: "I have enough to submit this. Our team will verify any missing details."

### 6. REMOVE "I CAN'T ACCESS RECORDS" LANGUAGE
The agent's entire job is to access records. Remove all deflection phrases. Replace with actual EHR lookups or honest "let me note this for callback" language.

### 7. ADD MINOR PATIENT DETECTION
If DOB shows age < 18: require guardian on line, route to clinical team for any scheduling/reactivation.

### 8. ADD MED LIST VERIFICATION
After finding patient, pull their med list. If requested med isn't on the list: "I don't see [Med] on your active medication list. Your chart shows [actual meds]. Let me check with your provider's team."

### 9. ADD PROVIDER MISMATCH FLAGGING
If caller names a different provider than EHR shows: flag it, don't silently accept.

### 10. FIX WEBSOCKET DROPS
14 conversations died with empty responses. Increase timeouts, add keepalive, ensure agent always has a follow-up message after any tool call.

---

## SECTION 5: QUESTIONS FOR PRIME PSYCHIATRY

1. **Prescription confirmation:** Once we're in a patient's records, can we confirm their medication list to them? (Currently agent sometimes can, sometimes says "can't access records")
2. **Prescribing provider from EHR:** Do we confirm what the patient says, or do we tell them what EHR shows? (Recommend: always show EHR, ask patient to confirm)
3. **Refill turnaround communication:** Should we say "1-3 business days" or "up to 48 hours" for non-controlled? Controlled?
4. **Appointment types visible:** Can the agent see appointment types (med management, therapy, eval)? Should it be able to consult on them?
5. **Phone number verification:** Should agent confirm "Is [number on file] still good?" or ask for current number?
6. **ROI for referrals:** For HMO patients needing PCP referral — do we send ROI by email or text? What's the process?
7. **Prior authorization:** When a pharmacy calls about prior auth, what info should the agent provide? Should it explain the PA process to patients?
8. **Prescription not at pharmacy:** If patient says "my prescription isn't at the pharmacy" — what's the workflow?
9. **Provider DEA numbers:** Should these ever be given out, or only NPI?
10. **Transfer to live staff:** During office hours, should the agent be able to warm-transfer to a live person for complex cases?

---

## SECTION 6: MISSING TEST SCENARIOS (for next round)

### Normal cases needed (not just edge cases):
- Simple new patient booking (happy path)
- Simple existing patient follow-up scheduling
- Simple refill for non-controlled, everything matches
- Simple insurance inquiry ("do you take Aetna?")
- Simple "what are your hours/locations?" FAQ
- Patient asking about telehealth options
- Patient confirming appointment details

### Additional edge cases:
- Pharmacy says med not found / not at pharmacy
- Prior authorization explanation
- Patient asking about copay/cost
- Patient asking to change pharmacy
- Patient reporting side effects (route to clinical)
- Patient asking about medication interactions
- Emergency/crisis caller (suicide ideation protocol)
- Patient wants records transferred to another provider
- Patient asking about lab work / pre-appointment requirements
- Caller with heavy accent / speech impediment
- Caller who is elderly and confused
- Multiple requests in one call (refill + appointment + billing question)

---

*Report generated by Claude acting as healthcare professional evaluator. All judgements based on clinical standards for psychiatric practice front-desk operations.*
