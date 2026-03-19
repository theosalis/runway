"""
EHR INTEGRATION STRESS TEST — 120 Scenarios (LLM-Judge Edition)
================================================================
Message flows match the agent's natural conversation order:
  1. Reason for call + medication name (combined)
  2. Dosage
  3. Name + DOB (when agent asks for identity)
  4. Provider, pharmacy, confirmation

All dates relative to: March 18, 2026.
"""

from client import contains_text, contains_all, not_contains

# ═══════════════════════════════════════════════════════════════
# A. PATIENT VERIFICATION — EHR READ (17 tests)
# ═══════════════════════════════════════════════════════════════

A01_REAL_PATIENT_CORRECT_DOB = {
    "test_name": "A01_maria_rodriguez_correct_name_dob",
    "messages": [
        "I need to refill my Lexapro.",
        "10 milligrams.",
        "Maria Rodriguez, date of birth June 15, 1988.",
        "R-O-D-R-I-G-U-E-Z.",
        "Yes that's correct.",
        "Dr. Airuehia.",
        "CVS on Preston Road in Frisco, 972-555-1234.",
        "Yes, that's all correct.",
        "No, that's everything.",
    ],
    "pass_criteria": "Agent must successfully verify Maria Rodriguez (DOB 6/15/1988) in the EHR, confirm her identity, and proceed with the refill flow. By the end, the refill should be submitted with 48-hour turnaround mentioned for non-controlled medication.",
    "severity": "high",
    "context": "EHR: Maria Rodriguez, DOB 1988-06-15, provider Efosa Airuehia (MD), active meds: Lexapro 10mg, Buspar 15mg.",
    "expected_nodes": [],
}

A02_REAL_PATIENT_WRONG_DOB = {
    "test_name": "A02_maria_rodriguez_wrong_dob",
    "messages": [
        "I need to refill my Lexapro.",
        "10mg.",
        "Maria Rodriguez, date of birth June 15, 1989.",
        "I'm sure it's 1989.",
        "Hmm, could it be 1988?",
        "Yes that's me.",
    ],
    "pass_criteria": "Agent must NOT verify with wrong DOB (1989). Should indicate unable to find/match and ask caller to recheck. When caller corrects to 1988, agent should then successfully find the patient.",
    "severity": "high",
    "context": "EHR: Maria Rodriguez, DOB 1988-06-15 (NOT 1989).",
    "expected_nodes": [],
}

A03_REAL_PATIENT_MISSPELLED_NAME = {
    "test_name": "A03_david_chen_misspelled_as_chenn",
    "messages": [
        "I need to schedule a follow-up.",
        "David Chenn, C-H-E-N-N, DOB March 22, 1992.",
        "Oh wait, it's C-H-E-N. Just one N.",
        "Yes that's me.",
    ],
    "pass_criteria": "Agent should struggle to find 'David Chenn' and ask for re-confirmation of spelling. When corrected to 'Chen', agent should successfully locate the patient.",
    "severity": "medium",
    "context": "EHR: David Chen (one N), DOB 1992-03-22.",
    "expected_nodes": [],
}

A04_COMPLETELY_UNKNOWN_PATIENT = {
    "test_name": "A04_unknown_patient_not_in_system",
    "messages": [
        "I'd like to schedule an appointment.",
        "Franklin Washington, DOB January 1, 1970.",
        "W-A-S-H-I-N-G-T-O-N.",
        "I'm definitely a patient. I've been going there for years.",
        "Okay, I guess I need to register as new then.",
    ],
    "pass_criteria": "Agent must indicate Franklin Washington cannot be found. Must NOT fabricate a match. Must offer new patient registration or calling the office.",
    "severity": "high",
    "context": "Franklin Washington does NOT exist in the EHR.",
    "expected_nodes": [],
}

A05_SARAH_BROWN_INACTIVE_MINOR = {
    "test_name": "A05_sarah_brown_minor_inactive_record",
    "messages": [
        "I need to schedule an appointment for my daughter.",
        "Sarah Brown, date of birth April 12, 2010.",
        "Yes, she's 15 years old. She used to be a patient.",
        "I'm her mother, Lisa Brown.",
        "We'd like to reactivate her as a patient.",
    ],
    "pass_criteria": "Agent must recognize Sarah Brown as a minor (DOB 2010, age 15) and that her record is inactive. Must require parent/guardian involvement. Should route to office team for reactivation.",
    "severity": "critical",
    "context": "EHR: Sarah Brown, DOB 2010-04-12, INACTIVE, minor.",
    "expected_nodes": [],
}

A06_DOB_OFF_BY_ONE_YEAR = {
    "test_name": "A06_emily_park_dob_off_by_one_year",
    "messages": [
        "I need to refill my Zoloft.",
        "100mg.",
        "Emily Park, DOB February 14, 1996.",
        "Hmm, it might be 1995.",
        "Yes, 1995 is correct.",
    ],
    "pass_criteria": "Agent must NOT match with DOB 1996 (real is 1995). When corrected to 1995, should find the patient.",
    "severity": "high",
    "context": "EHR: Emily Park, DOB 1995-02-14 (NOT 1996).",
    "expected_nodes": [],
}

A07_SIMILAR_NAMES_DAVID_VS_JAMES_WILSON = {
    "test_name": "A07_similar_names_wilson_disambiguation",
    "messages": [
        "I need a medication refill.",
        "Vyvanse, 40mg.",
        "Wilson. My last name is Wilson.",
        "David Wilson, DOB September 30, 1982.",
        "Yes that's me.",
    ],
    "pass_criteria": "When only last name given, agent should ask for first name and DOB. After getting full info, should correctly identify David Wilson.",
    "severity": "medium",
    "context": "EHR has David Wilson (1982-09-30) and James Wilson (1978-09-30).",
    "expected_nodes": [],
}

A08_SIMILAR_NAMES_MARIA_DISAMBIGUATION = {
    "test_name": "A08_similar_names_maria_rodriguez_vs_garcia",
    "messages": [
        "I need to schedule an appointment.",
        "Maria. M-A-R-I-A.",
        "Oh sorry. Maria Rodriguez, June 15, 1988.",
        "Yes, that's correct.",
    ],
    "pass_criteria": "When only first name given, agent should request full name + DOB. After getting full info, should correctly identify Maria Rodriguez.",
    "severity": "medium",
    "context": "EHR has Maria Rodriguez (1988-06-15) and Maria Garcia (1995-05-18).",
    "expected_nodes": [],
}

A09_EXISTING_BUT_NOT_FOUND_OFFER_NEW = {
    "test_name": "A09_claims_existing_not_found_offer_new_patient",
    "messages": [
        "I'm an existing patient, I need my meds refilled.",
        "Lexapro, 10mg.",
        "Amanda Chen, DOB December 1, 1985.",
        "I'm positive I'm a patient. I saw someone last month.",
        "Fine, how do I become a new patient then?",
    ],
    "pass_criteria": "Agent must indicate Amanda Chen is not found. Must NOT fabricate a match. Should offer new patient registration or office contact.",
    "severity": "high",
    "context": "Amanda Chen does NOT exist in the EHR.",
    "expected_nodes": [],
}

A10_JOHN_SMITH_ORIGINAL_PATIENT = {
    "test_name": "A10_john_smith_original_patient_no_provider",
    "messages": [
        "I need to schedule an appointment.",
        "John Smith, March 15, 1985.",
        "I don't remember who my provider is.",
        "Yes, I'm an existing patient.",
    ],
    "pass_criteria": "Agent should find John Smith. When caller doesn't remember provider, should check EHR (no provider assigned) and handle gracefully.",
    "severity": "medium",
    "context": "EHR: John Smith, DOB 1985-03-15, active. No provider/meds/appointments.",
    "expected_nodes": [],
}

A11_JANE_DOE_ORIGINAL_PATIENT = {
    "test_name": "A11_jane_doe_original_patient",
    "messages": [
        "I want to check when my next appointment is.",
        "Jane Doe, DOB July 22, 1990.",
        "That's all I needed.",
    ],
    "pass_criteria": "Agent should find Jane Doe and check for appointments. None exist — should indicate none found and offer to schedule.",
    "severity": "low",
    "context": "EHR: Jane Doe, DOB 1990-07-22, active. No appointments.",
    "expected_nodes": [],
}

A12_ROBERT_JOHNSON_DOB_CHECK = {
    "test_name": "A12_robert_johnson_correct_dob",
    "messages": [
        "I need to refill a medication but I'm not sure which ones I'm on.",
        "Robert Johnson, November 3, 1978.",
        "Can you check what medications I have on file?",
    ],
    "pass_criteria": "Agent should find Robert Johnson and check med list. No meds on file — should indicate and suggest contacting provider.",
    "severity": "medium",
    "context": "EHR: Robert Johnson, DOB 1978-11-03, active. No meds on file.",
    "expected_nodes": [],
}

A13_CALLER_GIVES_NICKNAME = {
    "test_name": "A13_caller_uses_nickname_bob_for_robert_taylor",
    "messages": [
        "I need to refill my Concerta.",
        "36mg.",
        "Bob Taylor, July 4, 1982.",
        "Sorry, Robert Taylor. Bob is my nickname.",
        "That's me.",
    ],
    "pass_criteria": "Agent may not find 'Bob Taylor'. When corrected to 'Robert Taylor', should successfully find the patient.",
    "severity": "medium",
    "context": "EHR: Robert Taylor (not Bob), DOB 1982-07-04.",
    "expected_nodes": [],
}

A14_HIPAA_DENY_PATIENT_STATUS = {
    "test_name": "A14_hipaa_cannot_confirm_patient_status",
    "messages": [
        "I'm calling to check if my husband David Chen is a patient there.",
        "His DOB is March 22, 1992.",
        "Can you at least tell me if he has an appointment?",
        "Fine.",
    ],
    "pass_criteria": "Agent must NEVER confirm or deny patient status to third-party caller. Must cite privacy/HIPAA. Must not reveal appointment, provider, or any patient data — even with correct DOB.",
    "severity": "critical",
    "context": "David Chen IS in EHR but caller is third party. HIPAA prohibits confirming/denying.",
    "expected_nodes": [],
}

A15_MULTIPLE_PATIENTS_SAME_LAST_NAME = {
    "test_name": "A15_multiple_patients_last_name_only",
    "messages": [
        "I need an appointment. Last name is Davis.",
        "Emily Davis, December 8, 1988.",
        "That's me.",
    ],
    "pass_criteria": "Last name only → ask for first name + DOB. After full info, verify Emily Davis.",
    "severity": "low",
    "context": "EHR: Emily Davis, DOB 1988-12-08.",
    "expected_nodes": [],
}

A16_PATRICIA_LOPEZ_RETURNING_AFTER_14_MONTHS = {
    "test_name": "A16_patricia_lopez_long_gap_returning_patient",
    "messages": [
        "I used to be a patient and I want to come back.",
        "Patricia Lopez, March 25, 1986.",
        "It's been over a year since I've been in.",
        "Yes, I'd like to schedule a new evaluation.",
    ],
    "pass_criteria": "Agent should find Patricia Lopez, recognize 14+ month gap (last visit Jan 21, 2025), and recommend 60-minute evaluation rather than standard follow-up.",
    "severity": "high",
    "context": "EHR: Patricia Lopez, last appointment January 21, 2025 (~14 months ago).",
    "expected_nodes": [],
}

A17_FAKE_PATIENTS_BATCH = {
    "test_name": "A17_batch_fake_patients_not_found",
    "messages": [
        "I need a medication refill.",
        "Zoloft, 50mg.",
        "Samantha Williams, DOB May 5, 1993.",
        "That's definitely my name. S-A-M-A-N-T-H-A.",
        "I guess I'll call the office during business hours.",
    ],
    "pass_criteria": "Agent must indicate not found and NOT fabricate a match. Offer alternatives.",
    "severity": "medium",
    "context": "Samantha Williams does NOT exist in the EHR.",
    "expected_nodes": [],
}

# ═══════════════════════════════════════════════════════════════
# B. PROVIDER VERIFICATION & CROSS-REFERENCE (16 tests)
# ═══════════════════════════════════════════════════════════════

B01_CORRECT_PROVIDER_CONFIRMED = {"test_name": "B01_david_chen_correct_provider_thinh_vu", "messages": ["I need to refill my Wellbutrin.", "150mg.", "David Chen, March 22, 1992.", "C-H-E-N.", "Dr. Thinh Vu.", "CVS at Preston and Main in Plano, 972-555-3333.", "Yes that's right.", "No, that's all."], "pass_criteria": "Agent should verify David Chen, confirm Thinh Vu matches EHR, process Wellbutrin 150mg as standard non-controlled refill with 48-hour turnaround.", "severity": "medium", "context": "EHR: David Chen, provider Thinh Vu (MD). Wellbutrin 150mg on file, non-controlled.", "expected_nodes": []}

B02_WRONG_PROVIDER_EHR_MISMATCH = {"test_name": "B02_david_chen_names_wrong_provider", "messages": ["I need to refill my Wellbutrin.", "150mg.", "David Chen, DOB March 22, 1992.", "My provider is Dr. Airuehia.", "Oh really? Maybe it is Dr. Vu then.", "Yes, Dr. Thinh Vu."], "pass_criteria": "Caller says Airuehia but EHR shows Thinh Vu. Agent must flag the mismatch. Must NOT silently accept wrong provider.", "severity": "high", "context": "EHR: David Chen's provider is Thinh Vu (MD), NOT Airuehia.", "expected_nodes": []}

B03_CALLER_DOESNT_REMEMBER_PROVIDER = {"test_name": "B03_emily_park_doesnt_remember_provider", "messages": ["I need to refill my Zoloft.", "100mg.", "Emily Park, February 14, 1995.", "I honestly can't remember my provider's name.", "Oh yes, that sounds right.", "Walgreens on Custer Road in Plano, 972-555-4444.", "Yes.", "That's all."], "pass_criteria": "When caller can't remember, agent should pull provider from EHR (Jennifer Sackley NP) and inform caller. Zoloft is non-controlled — NP can handle without supervisor.", "severity": "medium", "context": "EHR: Emily Park, provider Jennifer Sackley (NP). Zoloft 100mg, non-controlled.", "expected_nodes": []}

B04_PROVIDER_NOT_ON_ROSTER = {"test_name": "B04_caller_names_provider_not_on_roster", "messages": ["I need to refill my Lexapro.", "10mg.", "Maria Rodriguez, June 15, 1988.", "My provider is Dr. Roberts.", "Are you sure? I thought his name was Roberts.", "Okay, I'll go with whoever is in your system."], "pass_criteria": "No Dr. Roberts on roster. Must flag and inform caller EHR shows Efosa Airuehia.", "severity": "high", "context": "EHR: Maria Rodriguez's provider is Efosa Airuehia (MD). No Dr. Roberts exists.", "expected_nodes": []}

B05_DR_FOWLER_IS_NP_NOT_MD = {"test_name": "B05_caller_says_dr_fowler_but_np", "messages": ["I need to refill my Xanax.", "0.5 milligrams.", "Sarah Mitchell, November 8, 1985.", "Dr. Fowler is my prescriber.", "Oh, he's a nurse practitioner? I didn't know that."], "pass_criteria": "Must correctly identify Zachary Fowler as NP, not MD. Xanax is C4 → must mention supervisor routing (Thinh Vu).", "severity": "high", "context": "Zachary Fowler is NP. Xanax 0.5mg is C4. Fowler's supervisor: Thinh Vu (MD).", "expected_nodes": []}

B06_DR_VU_DISAMBIGUATION_MULTIPLE = {"test_name": "B06_dr_vu_three_providers_disambiguation", "messages": ["I need to refill my Wellbutrin.", "150mg.", "David Chen, March 22, 1992.", "My provider is Dr. Vu.", "It's Dr. Thinh Vu.", "Yes that's right."], "pass_criteria": "Multiple Vus on staff (Thinh MD, Tina DO, Thai Thanh MD). Must disambiguate when caller says 'Dr. Vu'.", "severity": "medium", "context": "3 providers named Vu. David Chen's actual provider is Thinh Vu.", "expected_nodes": []}

B07_DR_AIR_SHORTENING = {"test_name": "B07_caller_says_dr_air_for_airuehia", "messages": ["I need to refill my Lamictal.", "I'm not sure of the dose.", "Michael Brown, April 18, 1975.", "My doctor is Dr. Air. A-I-R.", "Yes, that's the one. I can never pronounce his name."], "pass_criteria": "Should recognize 'Dr. Air' = Efosa Airuehia (common shortening). Should not reject outright.", "severity": "low", "context": "Michael Brown, provider Efosa Airuehia. 'Dr. Air' is common shortening.", "expected_nodes": []}

B08_TINA_VU_DO_NOT_MD = {"test_name": "B08_jennifer_adams_tina_vu_is_do", "messages": ["I need to refill my Prozac.", "40mg.", "Jennifer Adams, May 30, 1980.", "My doctor is Dr. Tina Vu.", "Yes."], "pass_criteria": "Tina Vu is DO — 'Dr.' is acceptable. Should not flag mismatch.", "severity": "low", "context": "Jennifer Adams, provider Tina Vu (DO). Prozac 40mg.", "expected_nodes": []}

B09_NP_PROVIDER_EXPLICIT = {"test_name": "B09_robert_taylor_knows_np_harley_narvaez", "messages": ["I need to refill my Concerta.", "36mg.", "Robert Taylor, July 4, 1982.", "My provider is Harley Narvaez. I know he's a nurse practitioner.", "Yes."], "pass_criteria": "Concerta is C2, Narvaez is NP. MUST mention supervisor routing to Thinh Vu.", "severity": "critical", "context": "Robert Taylor, Concerta 36mg (C2), Narvaez (NP), supervisor: Thinh Vu (MD).", "expected_nodes": []}

B10_CHRISTINA_FLOREANI_MD = {"test_name": "B10_patricia_lopez_provider_floreani", "messages": ["I want to schedule a follow-up.", "Patricia Lopez, March 25, 1986.", "Dr. Floreani. Christina Floreani.", "How long has it been since my last visit?"], "pass_criteria": "Should confirm Floreani. When asked about last visit, report January 2025 (~14 months). Should note long gap and recommend full evaluation.", "severity": "high", "context": "Patricia Lopez, provider Floreani (MD). Last appt January 21, 2025.", "expected_nodes": []}

B11_CALLER_KNOWS_BOTH_NP_AND_SUPERVISOR = {"test_name": "B11_caller_mentions_both_np_and_md", "messages": ["I need to refill my Vyvanse.", "40mg.", "James Wilson, September 30, 1978.", "My NP is Kimberley Gardner but Dr. Airuehia supervises.", "Yes."], "pass_criteria": "Should confirm Gardner/Airuehia NP/supervisor relationship is correct. Vyvanse is C2 — acknowledge supervisor routing.", "severity": "medium", "context": "James Wilson, Vyvanse 40mg (C2), Gardner (NP), supervisor: Airuehia (MD).", "expected_nodes": []}

B12_CHERYLONDA_RAMZY_LOOKUP = {"test_name": "B12_provider_cherylonda_ramzy_npi", "messages": ["I'm calling from a pharmacy. I need the NPI for one of your providers.", "The prescriber's name is Cherylonda Ramzy.", "R-A-M-Z-Y.", "Thank you."], "pass_criteria": "Should provide NPI 1528568227 for Cherylonda Ramzy.", "severity": "high", "context": "Cherylonda Ramzy NPI: 1528568227.", "expected_nodes": []}

B13_SANDRA_BIALOSE_LOOKUP = {"test_name": "B13_pharmacy_asks_sandra_bialose", "messages": ["Hi, I'm from Walgreens. I need the NPI for Sandra Bialose.", "B-I-A-L-O-S-E.", "Thank you."], "pass_criteria": "Should provide NPI 1891305827 for Sandra Bialose.", "severity": "high", "context": "Sandra Bialose NPI: 1891305827.", "expected_nodes": []}

B14_CARMEN_FERREIRA_LOPEZ_NP = {"test_name": "B14_caller_names_carmen_ferreira_lopez", "messages": ["I need to schedule with Carmen.", "Carmen Ferreira-López.", "She's a nurse practitioner, right?", "Perfect."], "pass_criteria": "Should confirm Carmen Ferreira-López is NP. Supervisor: Thinh Vu.", "severity": "low", "context": "Carmen Ferreira-López (NP), supervisor: Thinh Vu (MD).", "expected_nodes": []}

B15_MAXINE_ZARBINIAN_PA = {"test_name": "B15_maxine_zarbinian_physician_assistant", "messages": ["My provider is Maxine Zarbinian. Is she a doctor?", "So who supervises her for controlled medications?", "Got it. Thanks."], "pass_criteria": "Should clarify Zarbinian is PA, not doctor. Supervisor: Thinh Vu (MD).", "severity": "medium", "context": "Maxine Zarbinian (PA), supervisor: Thinh Vu (MD).", "expected_nodes": []}

B16_FAKE_PROVIDER_DR_PATEL = {"test_name": "B16_caller_names_nonexistent_dr_patel", "messages": ["I need a medication refill. My doctor is Dr. Patel.", "Latuda.", "Lisa Nguyen, December 25, 1990.", "I'm sure it's Dr. Patel.", "Hmm, maybe I'm wrong. Who does your system show?"], "pass_criteria": "No Dr. Patel on roster. EHR shows Heidi De Diego (NP) for Lisa Nguyen. Must flag mismatch.", "severity": "high", "context": "Lisa Nguyen, provider Heidi De Diego (NP). No Dr. Patel.", "expected_nodes": []}

# ═══════════════════════════════════════════════════════════════
# C. MEDICATION REFILL WITH EHR VALIDATION (22 tests)
# ═══════════════════════════════════════════════════════════════

C01_LEXAPRO_10MG_EXACT_MATCH = {"test_name": "C01_maria_rodriguez_lexapro_10mg_exact", "messages": ["I need to refill my Lexapro.", "10 milligrams.", "Maria Rodriguez, June 15, 1988.", "Dr. Airuehia.", "CVS on Preston Road in Frisco, 972-555-1234.", "Yes.", "No that's all."], "pass_criteria": "Everything matches EHR. Standard non-controlled refill, 48-hour turnaround. No supervisor needed.", "severity": "medium", "context": "Maria Rodriguez, Lexapro 10mg, Airuehia (MD). Non-controlled.", "expected_nodes": []}

C02_LEXAPRO_WRONG_DOSE_20MG = {"test_name": "C02_maria_rodriguez_lexapro_wrong_dose_20mg", "messages": ["I need to refill my Lexapro.", "20 milligrams.", "Maria Rodriguez, June 15, 1988.", "Are you sure? I thought my doctor increased it.", "Okay, I guess it's still 10mg then."], "pass_criteria": "EHR shows 10mg, caller says 20mg. Agent MUST flag dosage discrepancy and trust EHR. Must NOT silently process 20mg.", "severity": "high", "context": "EHR: Lexapro 10mg (NOT 20mg).", "expected_nodes": []}

C03_BUSPAR_15MG_SECOND_MED = {"test_name": "C03_maria_rodriguez_buspar_15mg_match", "messages": ["I need to refill my Buspar.", "15mg.", "Maria Rodriguez, June 15, 1988.", "Dr. Airuehia.", "Same pharmacy — CVS on Preston in Frisco.", "Yes.", "That's all."], "pass_criteria": "Buspar 15mg matches EHR. Standard non-controlled refill, 48-hour turnaround.", "severity": "medium", "context": "Maria Rodriguez, Buspar 15mg, non-controlled.", "expected_nodes": []}

C04_MARIA_REQUESTS_ADDERALL_NOT_ON_LIST = {"test_name": "C04_maria_rodriguez_requests_adderall_not_on_med_list", "messages": ["I need to refill my Adderall.", "20mg.", "Maria Rodriguez, June 15, 1988.", "Are you sure it's not on file? My friend told me I was on it."], "pass_criteria": "Adderall NOT on Maria's med list (only Lexapro, Buspar). Must flag and cannot refill. Suggest contacting provider.", "severity": "critical", "context": "Maria Rodriguez meds: Lexapro 10mg, Buspar 15mg ONLY. No Adderall.", "expected_nodes": []}

C05_DAVID_CHEN_ADDERALL_XR_20MG_CONTROLLED = {"test_name": "C05_david_chen_adderall_xr_20mg_controlled", "messages": ["I need to refill my Adderall XR.", "20mg.", "David Chen, March 22, 1992.", "Dr. Thinh Vu.", "About three weeks ago.", "CVS on Legacy Drive in Plano, 972-555-5555.", "Yes.", "That's all."], "pass_criteria": "Adderall XR 20mg matches EHR. C2 controlled, MD provider — no supervisor needed. Must verify 90-day rule. 1-3 business day turnaround.", "severity": "high", "context": "David Chen, Adderall XR 20mg (C2), Thinh Vu (MD). No appointment in seed data.", "expected_nodes": []}

C06_DAVID_CHEN_WELLBUTRIN_NON_CONTROLLED = {"test_name": "C06_david_chen_wellbutrin_150mg_standard", "messages": ["I need to refill my Wellbutrin.", "150mg.", "David Chen, March 22, 1992.", "Dr. Thinh Vu.", "Walgreens on Park Boulevard in Plano, 972-555-6666.", "Yes.", "No that's all."], "pass_criteria": "Wellbutrin 150mg matches EHR, non-controlled. Standard 48-hour turnaround.", "severity": "medium", "context": "David Chen, Wellbutrin 150mg, non-controlled.", "expected_nodes": []}

C07_DAVID_CHEN_WRONG_ADDERALL_DOSE = {"test_name": "C07_david_chen_adderall_30mg_ehr_shows_20mg", "messages": ["I need to refill my Adderall.", "30 milligrams.", "David Chen, March 22, 1992.", "I'm pretty sure my doctor increased it last time.", "Fine, go with what's on file."], "pass_criteria": "EHR shows 20mg, caller says 30mg. Agent MUST flag discrepancy and trust EHR. Must NOT process 30mg.", "severity": "high", "context": "EHR: Adderall XR 20mg (NOT 30mg).", "expected_nodes": []}

C08_SARAH_MITCHELL_XANAX_NP_SUPERVISOR = {"test_name": "C08_sarah_mitchell_xanax_np_must_route_supervisor", "messages": ["I need to refill my Xanax.", "0.5 milligrams.", "Sarah Mitchell, November 8, 1985.", "My provider is Zachary Fowler.", "CVS in Southlake, 817-555-1111.", "Yes.", "That's all."], "pass_criteria": "Xanax C4 + NP Fowler → MUST route to supervisor Thinh Vu. Must clearly communicate supervisor involvement.", "severity": "critical", "context": "Sarah Mitchell, Xanax 0.5mg (C4), Fowler (NP), supervisor: Thinh Vu (MD).", "expected_nodes": []}

C09_JAMES_WILSON_VYVANSE_C2_NP_SUPERVISOR = {"test_name": "C09_james_wilson_vyvanse_c2_np_must_route_supervisor", "messages": ["I need to refill my Vyvanse.", "40mg.", "James Wilson, September 30, 1978.", "Kimberley Gardner is my provider.", "CVS on Main Street in Frisco, 972-555-7777.", "Yes.", "No, that's it."], "pass_criteria": "Vyvanse C2 + NP Gardner → MUST route to supervisor Efosa Airuehia. NPs cannot sign C2.", "severity": "critical", "context": "James Wilson, Vyvanse 40mg (C2), Gardner (NP), supervisor: Airuehia (MD).", "expected_nodes": []}

C10_EMILY_PARK_ZOLOFT_NP_CAN_HANDLE = {"test_name": "C10_emily_park_zoloft_np_no_supervisor_needed", "messages": ["I need to refill my Zoloft.", "100mg.", "Emily Park, February 14, 1995.", "Jennifer Sackley.", "Walgreens on Coit Road in Richardson, 972-555-8888.", "Yes.", "That's all."], "pass_criteria": "Zoloft non-controlled + NP Sackley → NP CAN handle. NO supervisor needed. Agent must NOT mention supervisor routing.", "severity": "high", "context": "Emily Park, Zoloft 100mg (non-controlled), Sackley (NP).", "expected_nodes": []}

C11_ROBERT_TAYLOR_CONCERTA_C2_NP = {"test_name": "C11_robert_taylor_concerta_c2_np_supervisor_route", "messages": ["I need to refill my Concerta.", "36mg.", "Robert Taylor, July 4, 1982.", "Harley Narvaez is my provider. He's a nurse practitioner.", "CVS in The Colony, 972-555-9999.", "Yes.", "That's all."], "pass_criteria": "Concerta C2 + NP Narvaez → MUST route to supervisor Thinh Vu. Last appt Feb 25 = within 90 days.", "severity": "critical", "context": "Robert Taylor, Concerta 36mg (C2), Narvaez (NP), supervisor: Thinh Vu. Last appt Feb 25, 2026.", "expected_nodes": []}

C12_PATRICIA_LOPEZ_KLONOPIN_90DAY_BLOCK = {"test_name": "C12_patricia_lopez_klonopin_90day_hard_block", "messages": ["I need to refill my Klonopin.", "I don't remember the dose.", "Patricia Lopez, March 25, 1986.", "Dr. Floreani.", "Hmm, maybe a couple months ago?"], "pass_criteria": "Klonopin C4, last visit Jan 2025 (14+ months). HARD BLOCK — must require appointment before controlled refill. Non-negotiable.", "severity": "critical", "context": "Patricia Lopez, Klonopin (C4), last appt January 21, 2025 = 14 months ago. HARD 90-DAY BLOCK.", "expected_nodes": []}

C13_PATRICIA_LOPEZ_SEROQUEL_NON_CONTROLLED_FLAG = {"test_name": "C13_patricia_lopez_seroquel_non_controlled_still_flagged", "messages": ["I need to refill my Seroquel.", "Patricia Lopez, March 25, 1986.", "Dr. Floreani.", "I'm not sure when my last visit was."], "pass_criteria": "Seroquel non-controlled (no hard block), but 14+ months is very long. Agent should flag the gap and recommend scheduling.", "severity": "high", "context": "Patricia Lopez, Seroquel (non-controlled), last appt January 21, 2025.", "expected_nodes": []}

C14_ETHAN_COOPER_SUBOXONE_C3_NP_SUPERVISOR = {"test_name": "C14_ethan_cooper_suboxone_c3_np_route_supervisor", "messages": ["I need to refill my Suboxone.", "Ethan Cooper, August 3, 1991.", "My provider is Sabrina Labvah.", "I was seen about 7 weeks ago.", "CVS on Eldorado in Frisco, 972-555-2222.", "Yes.", "That's all."], "pass_criteria": "Suboxone C3 + NP Labvah → MUST route to supervisor Efosa Airuehia. Last visit ~51 days = within 90.", "severity": "critical", "context": "Ethan Cooper, Suboxone (C3), Labvah (NP), supervisor: Airuehia. Last appt Jan 26, 2026.", "expected_nodes": []}

C15_DANIEL_GARCIA_HYDROXYZINE_NP_CAN_HANDLE = {"test_name": "C15_daniel_garcia_hydroxyzine_np_no_supervisor", "messages": ["I need to refill my Hydroxyzine.", "Daniel Garcia, October 12, 1998.", "Ruth Onsotti is my provider.", "I was seen about a week ago.", "CVS in Richardson, 972-555-3333.", "Yes.", "That's all."], "pass_criteria": "Hydroxyzine non-controlled + NP Onsotti → NP can handle. No supervisor. Last visit Mar 10 = recent. Standard refill.", "severity": "high", "context": "Daniel Garcia, Hydroxyzine (non-controlled), Onsotti (NP). Last appt Mar 10, 2026.", "expected_nodes": []}

C16_FAKE_MEDICATION_FLURBINOL = {"test_name": "C16_caller_requests_fake_medication_flurbinol", "messages": ["I need to refill my Flurbinol.", "F-L-U-R-B-I-N-O-L.", "My doctor prescribed it for anxiety."], "pass_criteria": "Flurbinol is not real. Agent should not recognize it. Must NOT fabricate information. Should ask to verify or route to clinical team.", "severity": "medium", "context": "Flurbinol does not exist.", "expected_nodes": []}

C17_CALLER_DOESNT_REMEMBER_DOSAGE = {"test_name": "C17_caller_forgets_dosage_agent_notes_it", "messages": ["I need to refill my Lexapro.", "I honestly don't remember my dosage.", "Maria Rodriguez, June 15, 1988.", "Dr. Airuehia.", "CVS on Preston in Frisco.", "Yes.", "That's all."], "pass_criteria": "When caller doesn't know dosage, agent should check EHR (10mg) and use that. Should still process the refill.", "severity": "medium", "context": "Maria Rodriguez, Lexapro 10mg on file.", "expected_nodes": []}

C18_RACHEL_KIM_NO_MEDS_ON_FILE = {"test_name": "C18_rachel_kim_no_meds_on_file", "messages": ["I need a medication refill.", "Lexapro 10mg.", "Rachel Kim, November 22, 1996.", "But I need it!"], "pass_criteria": "NO medications on file for Rachel Kim. Cannot refill what isn't prescribed. Must inform and direct to provider.", "severity": "critical", "context": "Rachel Kim, NO medications on file.", "expected_nodes": []}

C19_CORRECT_MED_WRONG_DOSE_BUSPAR = {"test_name": "C19_maria_rodriguez_buspar_wrong_dose_30mg", "messages": ["I need to refill my Buspar.", "30 milligrams.", "Maria Rodriguez, June 15, 1988.", "Okay I'll trust whatever you have."], "pass_criteria": "EHR shows 15mg, caller says 30mg. Must flag discrepancy and trust EHR.", "severity": "high", "context": "Maria Rodriguez, Buspar 15mg (NOT 30mg).", "expected_nodes": []}

C20_LISA_NGUYEN_LATUDA_NP_NON_CONTROLLED = {"test_name": "C20_lisa_nguyen_latuda_np_can_handle", "messages": ["I need to refill my Latuda.", "Lisa Nguyen, December 25, 1990.", "My provider is Heidi De Diego.", "I was seen about 3 weeks ago.", "Walgreens on Stonebrook in Frisco, 972-555-4444.", "Yes.", "That's all."], "pass_criteria": "Latuda non-controlled + NP De Diego → NP can handle. No supervisor. Last visit Feb 20 = within 90. Standard refill.", "severity": "high", "context": "Lisa Nguyen, Latuda (non-controlled), De Diego (NP). Last appt Feb 20, 2026.", "expected_nodes": []}

C21_MICHAEL_BROWN_TRAZODONE_REFILL = {"test_name": "C21_michael_brown_trazodone_non_controlled", "messages": ["I need to refill my Trazodone.", "I don't remember the dose. Can you check?", "Michael Brown, April 18, 1975.", "Dr. Airuehia.", "CVS in Richardson, 972-555-5555.", "Yes.", "That's all."], "pass_criteria": "Trazodone non-controlled, Airuehia MD. When caller doesn't know dose, check EHR. Last visit Feb 5 = 41 days, within 90. Standard refill.", "severity": "medium", "context": "Michael Brown, Trazodone, Airuehia (MD). Last appt Feb 5, 2026.", "expected_nodes": []}

C22_MICHAEL_BROWN_LAMICTAL_90DAY_EDGE = {"test_name": "C22_michael_brown_lamictal_non_controlled_within_90", "messages": ["I need to refill my Lamictal.", "Michael Brown, April 18, 1975.", "Dr. Airuehia.", "My last visit was early February I think.", "CVS in Plano, 972-555-6666.", "Yes.", "That's all."], "pass_criteria": "Lamictal non-controlled. Feb 5 = ~41 days, within 90. Process normally.", "severity": "medium", "context": "Michael Brown, Lamictal, last appt Feb 5, 2026.", "expected_nodes": []}

# ═══════════════════════════════════════════════════════════════
# D. 90-DAY RULE ENFORCEMENT (15 tests)
# ═══════════════════════════════════════════════════════════════

D01_ROBERT_TAYLOR_21_DAYS = {"test_name": "D01_robert_taylor_21_days_within_90", "messages": ["I need to refill my Concerta.", "36mg.", "Robert Taylor, July 4, 1982.", "Harley Narvaez is my NP.", "My last appointment was February 25th."], "pass_criteria": "Feb 25 = ~21 days, within 90. Should NOT block. Proceed (with NP→supervisor for C2).", "severity": "high", "context": "Robert Taylor, Concerta (C2), last appt Feb 25, 2026 = 21 days.", "expected_nodes": []}

D02_LISA_NGUYEN_26_DAYS = {"test_name": "D02_lisa_nguyen_26_days_within_90", "messages": ["I need to refill my Latuda.", "Lisa Nguyen, December 25, 1990.", "Heidi De Diego is my provider.", "I was seen February 20th."], "pass_criteria": "Feb 20 = ~26 days, within 90. Non-controlled. No block.", "severity": "medium", "context": "Lisa Nguyen, Latuda, last appt Feb 20, 2026.", "expected_nodes": []}

D03_MICHAEL_BROWN_41_DAYS = {"test_name": "D03_michael_brown_41_days_within_90", "messages": ["I need to refill my Lamictal.", "Michael Brown, April 18, 1975.", "Dr. Airuehia.", "My last visit was around February 5th."], "pass_criteria": "Feb 5 = ~41 days, within 90. Non-controlled. No block.", "severity": "medium", "context": "Michael Brown, Lamictal, last appt Feb 5, 2026.", "expected_nodes": []}

D04_KEVIN_MARTINEZ_11_DAYS = {"test_name": "D04_kevin_martinez_11_days_very_recent", "messages": ["I need to refill my Adderall.", "30mg.", "Kevin Martinez, January 20, 1987.", "Dr. Thinh Vu.", "I was just seen on March 7th."], "pass_criteria": "Mar 7 = ~11 days. Very recent. No 90-day issues.", "severity": "medium", "context": "Kevin Martinez, Adderall XR 30mg (C2), last appt Mar 7, 2026.", "expected_nodes": []}

D05_JENNIFER_ADAMS_6_DAYS = {"test_name": "D05_jennifer_adams_6_days_very_recent", "messages": ["I need to refill my Prozac.", "40mg.", "Jennifer Adams, May 30, 1980.", "Tina Vu.", "I was seen March 12th.", "Walgreens in Plano, 972-555-1111.", "Yes.", "That's all."], "pass_criteria": "Mar 12 = ~6 days. Non-controlled. No issues. Standard refill.", "severity": "medium", "context": "Jennifer Adams, Prozac 40mg, Tina Vu (DO), last appt Mar 12, 2026.", "expected_nodes": []}

D06_DANIEL_GARCIA_8_DAYS = {"test_name": "D06_daniel_garcia_8_days_recent", "messages": ["I need to refill my Hydroxyzine.", "Daniel Garcia, October 12, 1998.", "Ruth Onsotti.", "March 10th was my last visit."], "pass_criteria": "Mar 10 = ~8 days. Non-controlled. No issues.", "severity": "low", "context": "Daniel Garcia, Hydroxyzine, last appt Mar 10, 2026.", "expected_nodes": []}

D07_ETHAN_COOPER_51_DAYS = {"test_name": "D07_ethan_cooper_51_days_within_90", "messages": ["I need to refill my Suboxone.", "Ethan Cooper, August 3, 1991.", "Sabrina Labvah is my NP.", "January 26th was my last appointment."], "pass_criteria": "Jan 26 = ~51 days, within 90. C3 + NP = needs supervisor, but 90-day should PASS.", "severity": "high", "context": "Ethan Cooper, Suboxone (C3), last appt Jan 26, 2026.", "expected_nodes": []}

D08_PATRICIA_LOPEZ_14_MONTHS_HARD_BLOCK = {"test_name": "D08_patricia_lopez_14_months_controlled_hard_block", "messages": ["I need to refill my Klonopin.", "Patricia Lopez, March 25, 1986.", "Dr. Floreani.", "My last visit was... I don't remember exactly."], "pass_criteria": "Last visit Jan 2025 = 14 months. Klonopin C4. HARD BLOCK. Must require appointment before refill.", "severity": "critical", "context": "Patricia Lopez, Klonopin (C4), last appt January 21, 2025 = 14 months.", "expected_nodes": []}

D09_CALLER_CLAIMS_RECENT_EHR_SAYS_6_MONTHS = {"test_name": "D09_caller_lies_about_last_visit_ehr_contradicts", "messages": ["I need to refill my Klonopin.", "Patricia Lopez, March 25, 1986.", "I was just seen last week.", "What do you mean? I definitely came in."], "pass_criteria": "Caller claims last week but EHR shows Jan 2025 (14 months). Agent MUST trust EHR and enforce 90-day block. Cannot accept false claim.", "severity": "critical", "context": "Patricia Lopez, Klonopin (C4). EHR: Jan 2025. Caller falsely claims last week.", "expected_nodes": []}

D10_CALLER_CANT_REMEMBER_LAST_VISIT = {"test_name": "D10_caller_doesnt_remember_agent_checks_ehr", "messages": ["I need to refill my Concerta.", "36mg.", "Robert Taylor, July 4, 1982.", "I honestly have no idea when I was last seen.", "Okay, that sounds about right."], "pass_criteria": "Agent should check EHR for last appointment (Feb 25, 2026) and communicate to caller. Confirm within 90 days.", "severity": "medium", "context": "Robert Taylor, Concerta (C2), last appt Feb 25, 2026.", "expected_nodes": []}

D11_NO_APPOINTMENT_HISTORY = {"test_name": "D11_john_smith_no_appointments_controlled_block", "messages": ["I need a refill on Adderall.", "30mg.", "John Smith, March 15, 1985.", "I've never actually been seen there. My previous doctor prescribed it."], "pass_criteria": "No appointment history + controlled substance = MUST require scheduling before any controlled refill. Cannot transfer from outside.", "severity": "critical", "context": "John Smith, NO appointments, NO meds. Requesting controlled.", "expected_nodes": []}

D12_PATRICIA_SEROQUEL_NON_CONTROLLED_STILL_FLAGGED = {"test_name": "D12_patricia_lopez_seroquel_long_gap_non_controlled", "messages": ["I need to refill my Seroquel.", "Patricia Lopez, March 25, 1986.", "Dr. Floreani.", "I think it's been a while since I was last in."], "pass_criteria": "Seroquel non-controlled (no hard block), but 14+ months gap should be flagged. Recommend scheduling.", "severity": "high", "context": "Patricia Lopez, Seroquel (non-controlled), last appt Jan 2025.", "expected_nodes": []}

D13_KEVIN_MARTINEZ_UPCOMING_APPT = {"test_name": "D13_kevin_martinez_has_upcoming_appointment", "messages": ["I need to refill my Adderall.", "30mg.", "Kevin Martinez, January 20, 1987.", "Dr. Vu.", "I have an appointment coming up on March 20th too."], "pass_criteria": "Recent visit (Mar 7) + upcoming (Mar 20). Well within 90 days. Proceed.", "severity": "medium", "context": "Kevin Martinez, Adderall (C2), last appt Mar 7, upcoming Mar 20.", "expected_nodes": []}

D14_90DAY_BOUNDARY_EXACTLY_89_DAYS = {"test_name": "D14_hypothetical_exactly_at_90day_boundary", "messages": ["I need to refill my Concerta.", "36mg.", "Robert Taylor, DOB July 4, 1982.", "My last appointment was about 3 months ago, December 18th."], "pass_criteria": "Caller claims Dec 18 but EHR shows Feb 25. Agent should trust EHR (Feb 25 = within 90).", "severity": "high", "context": "Robert Taylor, Concerta (C2). ACTUAL last appt Feb 25, 2026. Caller claims Dec 18.", "expected_nodes": []}

D15_NO_MEDS_NO_APPTS_NEW_TO_PRACTICE = {"test_name": "D15_rachel_kim_no_meds_no_recent_appts", "messages": ["I need an Adderall prescription.", "Rachel Kim, November 22, 1996.", "I just transferred my care here."], "pass_criteria": "No meds, no appointments, requesting controlled. Must require appointment first. Cannot prescribe controlled without being seen.", "severity": "critical", "context": "Rachel Kim, NO meds, NO appointments. Requesting controlled.", "expected_nodes": []}

# ═══════════════════════════════════════════════════════════════
# E. NP → SUPERVISOR ROUTING (11 tests)
# ═══════════════════════════════════════════════════════════════

E01_FOWLER_XANAX_C4_TO_THINH_VU = {"test_name": "E01_fowler_xanax_c4_routes_to_thinh_vu", "messages": ["I need to refill my Xanax.", "0.5mg.", "Sarah Mitchell, November 8, 1985.", "My provider is Zachary Fowler."], "pass_criteria": "Xanax C4 + NP Fowler → MUST mention supervisor (Thinh Vu).", "severity": "critical", "context": "Xanax (C4), Fowler (NP), supervisor: Thinh Vu.", "expected_nodes": []}

E02_GARDNER_VYVANSE_C2_TO_AIRUEHIA = {"test_name": "E02_gardner_vyvanse_c2_routes_to_airuehia", "messages": ["I need to refill my Vyvanse.", "40mg.", "James Wilson, September 30, 1978.", "Kimberley Gardner is my provider."], "pass_criteria": "Vyvanse C2 + NP Gardner → MUST route to Efosa Airuehia.", "severity": "critical", "context": "Vyvanse (C2), Gardner (NP), supervisor: Airuehia.", "expected_nodes": []}

E03_SACKLEY_ZOLOFT_NO_SUPERVISOR = {"test_name": "E03_sackley_zoloft_non_controlled_np_handles", "messages": ["I need to refill my Zoloft.", "100mg.", "Emily Park, February 14, 1995.", "Jennifer Sackley is my provider."], "pass_criteria": "Zoloft non-controlled + NP → NP can handle. Must NOT mention supervisor.", "severity": "high", "context": "Zoloft (non-controlled), Sackley (NP).", "expected_nodes": []}

E04_NARVAEZ_CONCERTA_C2_TO_THINH_VU = {"test_name": "E04_narvaez_concerta_c2_routes_to_thinh_vu", "messages": ["I need to refill my Concerta.", "36mg.", "Robert Taylor, July 4, 1982.", "My provider is Harley Narvaez."], "pass_criteria": "Concerta C2 + NP Narvaez → MUST route to Thinh Vu.", "severity": "critical", "context": "Concerta (C2), Narvaez (NP), supervisor: Thinh Vu.", "expected_nodes": []}

E05_LABVAH_SUBOXONE_C3_TO_AIRUEHIA = {"test_name": "E05_labvah_suboxone_c3_routes_to_airuehia", "messages": ["I need to refill my Suboxone.", "Ethan Cooper, August 3, 1991.", "Sabrina Labvah is my NP."], "pass_criteria": "Suboxone C3 + NP Labvah → MUST route to Airuehia.", "severity": "critical", "context": "Suboxone (C3), Labvah (NP), supervisor: Airuehia.", "expected_nodes": []}

E06_ONSOTTI_HYDROXYZINE_NO_SUPERVISOR = {"test_name": "E06_onsotti_hydroxyzine_non_controlled_np_handles", "messages": ["I need to refill my Hydroxyzine.", "Daniel Garcia, October 12, 1998.", "Ruth Onsotti is my provider."], "pass_criteria": "Hydroxyzine non-controlled + NP → NP can handle. Must NOT mention supervisor.", "severity": "high", "context": "Hydroxyzine (non-controlled), Onsotti (NP).", "expected_nodes": []}

E07_DE_DIEGO_LATUDA_NO_SUPERVISOR = {"test_name": "E07_de_diego_latuda_non_controlled_np_handles", "messages": ["I need to refill my Latuda.", "Lisa Nguyen, December 25, 1990.", "My provider is Heidi De Diego."], "pass_criteria": "Latuda non-controlled + NP → NP can handle. Must NOT mention supervisor.", "severity": "high", "context": "Latuda (non-controlled), De Diego (NP).", "expected_nodes": []}

E08_NP_DOSE_INCREASE_CONTROLLED = {"test_name": "E08_np_controlled_dose_increase_still_needs_supervisor", "messages": ["I need to increase my Vyvanse dose.", "I'm currently on 40mg but I want to go up to 60mg.", "James Wilson, September 30, 1978.", "My NP is Kimberley Gardner."], "pass_criteria": "Vyvanse C2 dose change + NP = still needs supervisor (Airuehia). Dose changes on C2 still require MD.", "severity": "critical", "context": "Vyvanse (C2) dose change, Gardner (NP), supervisor: Airuehia.", "expected_nodes": []}

E09_MD_PROVIDER_NO_SUPERVISOR_NEEDED = {"test_name": "E09_md_provider_controlled_no_supervisor_routing", "messages": ["I need to refill my Adderall.", "20mg XR.", "David Chen, March 22, 1992.", "Dr. Thinh Vu is my provider."], "pass_criteria": "Adderall C2 but Thinh Vu is MD. NO supervisor needed. Must NOT mention supervisor.", "severity": "high", "context": "Adderall (C2), Thinh Vu (MD). MD handles C2 independently.", "expected_nodes": []}

E10_NP_NON_CONTROLLED_MED_CHANGE = {"test_name": "E10_np_non_controlled_med_change_no_supervisor", "messages": ["I'd like to increase my Zoloft dose.", "I'm on 100mg but want to go to 150mg.", "Emily Park, February 14, 1995.", "Jennifer Sackley is my NP."], "pass_criteria": "Zoloft non-controlled dose change + NP → no supervisor needed. Route as med change but no MD requirement.", "severity": "medium", "context": "Zoloft (non-controlled) dose change, Sackley (NP).", "expected_nodes": []}

E11_CALLER_ASKS_WHO_SUPERVISES = {"test_name": "E11_caller_asks_who_supervises_their_np", "messages": ["Who is the supervising doctor for my nurse practitioner?", "My NP is Zachary Fowler.", "And can that doctor handle my Xanax refill?"], "pass_criteria": "Should identify Thinh Vu as Fowler's supervisor. Confirm Vu can handle Xanax (C4).", "severity": "medium", "context": "Fowler (NP), supervisor: Thinh Vu (MD). Xanax C4.", "expected_nodes": []}

# ═══════════════════════════════════════════════════════════════
# F. APPOINTMENT BOOKING (10 tests)
# ═══════════════════════════════════════════════════════════════

F01_KEVIN_RESCHEDULE_UPCOMING = {"test_name": "F01_kevin_martinez_reschedule_march_20", "messages": ["I need to reschedule my appointment.", "Kevin Martinez, January 20, 1987.", "My current appointment is March 20th.", "Can we move it to the following week?", "Dr. Vu. Thinh Vu.", "Option 1.", "Great, thank you."], "pass_criteria": "Should find March 20 appointment, offer alternatives, and reschedule. No late cancel fee (>24hrs).", "severity": "medium", "context": "Kevin Martinez, upcoming appointment March 20, 2026.", "expected_nodes": []}

F02_KEVIN_CANCEL_NO_FEE = {"test_name": "F02_kevin_martinez_cancel_march_20_no_fee", "messages": ["I need to cancel my appointment.", "Kevin Martinez, January 20, 1987.", "March 20th.", "Work conflict.", "No, I don't want to reschedule right now.", "That's all."], "pass_criteria": "March 20 is 2 days away (>24hrs). NO late cancel fee. Should not mention fees.", "severity": "high", "context": "Today March 18. March 20 = >24hrs = no fee.", "expected_nodes": []}

F03_PATRICIA_RETURNING_60MIN_EVAL = {"test_name": "F03_patricia_lopez_returning_60min_eval", "messages": ["I'd like to schedule an appointment. I haven't been in over a year.", "Patricia Lopez, March 25, 1986.", "Dr. Floreani.", "In person at Frisco.", "Next week any day.", "Option 1.", "Thank you."], "pass_criteria": "14+ month gap. Must schedule 60-minute evaluation, NOT 20-minute follow-up.", "severity": "high", "context": "Patricia Lopez, last visit Jan 2025. Needs 60-min eval.", "expected_nodes": []}

F04_JENNIFER_ADAMS_STANDARD_FOLLOWUP = {"test_name": "F04_jennifer_adams_recent_visit_20min_followup", "messages": ["I'd like to schedule a follow-up.", "Jennifer Adams, May 30, 1980.", "Tina Vu.", "In person at Plano.", "Next week, any morning.", "Option 1.", "Thanks."], "pass_criteria": "Recent visit (Mar 12). Standard follow-up appropriate. Should NOT schedule 60-min eval.", "severity": "medium", "context": "Jennifer Adams, last visit March 12, 2026.", "expected_nodes": []}

F05_BRAND_NEW_PATIENT_FULL_INTAKE = {"test_name": "F05_brand_new_patient_create_and_book", "messages": ["I'd like to become a new patient.", "Alexandra Rivera.", "September 10, 1993.", "214-555-1234.", "alexandra.r@gmail.com", "Blue Cross Blue Shield PPO.", "Depression and insomnia.", "Psychiatric evaluation.", "Telehealth.", "No provider preference.", "Next week.", "Yes, I understand about the credit card on file.", "Option 1.", "Thank you!"], "pass_criteria": "New patient full intake. MUST mention credit card/ClearGage requirement. BCBS PPO accepted.", "severity": "high", "context": "New patient. BCBS PPO accepted. CC/ClearGage mandatory.", "expected_nodes": []}

F06_EXISTING_PATIENT_SKIP_CC = {"test_name": "F06_existing_patient_card_on_file_skip_cc", "messages": ["I need to schedule a follow-up.", "David Chen, March 22, 1992.", "Dr. Vu.", "In person at Plano.", "Next week, mornings.", "Option 1.", "That's all."], "pass_criteria": "Existing patient. Should schedule normally without CC gate re-trigger.", "severity": "low", "context": "David Chen, existing active patient.", "expected_nodes": []}

F07_MEDICAID_HARD_REJECTION_SCHEDULING = {"test_name": "F07_new_patient_medicaid_hard_rejection", "messages": ["I want to become a new patient.", "Carlos Mendez.", "February 14, 1990.", "I have Medicaid.", "Are you sure? I really need to see someone."], "pass_criteria": "Medicaid NEVER accepted. HARD rejection. Even when caller pleads, answer is no. Must NOT schedule or offer workarounds.", "severity": "critical", "context": "Medicaid = HARD REJECTION. No exceptions.", "expected_nodes": []}

F08_HMO_NEEDS_REFERRAL = {"test_name": "F08_hmo_plan_requires_pcp_referral", "messages": ["I want to become a new patient.", "Sarah Williams.", "October 5, 1988.", "I have United Healthcare HMO.", "I don't have a referral yet.", "Okay, I'll get one from my PCP."], "pass_criteria": "HMO requires PCP referral before scheduling. Must inform and cannot schedule without it.", "severity": "high", "context": "UHC HMO. Referral required.", "expected_nodes": []}

F09_TELEHEALTH_LOCATION_FLEXIBILITY = {"test_name": "F09_telehealth_no_location_constraint", "messages": ["I'd like to schedule a telehealth appointment.", "Emily Park, February 14, 1995.", "Jennifer Sackley.", "Med management follow-up.", "Next week, afternoons.", "Option 1.", "Thanks."], "pass_criteria": "Telehealth = no physical location needed. Should schedule with telehealth slots.", "severity": "low", "context": "Telehealth, no location constraint.", "expected_nodes": []}

F10_EXISTING_PATIENT_NO_CC_CLEARGAGE = {"test_name": "F10_existing_patient_no_card_mentions_cleargage", "messages": ["I need to schedule a new patient evaluation. I called before but never completed intake.", "Maria Garcia, May 18, 1995.", "PPO insurance.", "Anxiety.", "In person at Frisco.", "Next week.", "I don't have a credit card on file yet."], "pass_criteria": "No card on file. Must mention ClearGage portal for adding credit card. Cannot bypass CC requirement.", "severity": "high", "context": "Maria Garcia exists but no card. ClearGage is payment portal.", "expected_nodes": []}

# ═══════════════════════════════════════════════════════════════
# G. CANCEL/RESCHEDULE (10 tests)
# ═══════════════════════════════════════════════════════════════

G01_CANCEL_MORE_THAN_24HR_NO_FEE = {"test_name": "G01_cancel_2_days_out_no_late_fee", "messages": ["I need to cancel my appointment on March 20th.", "Kevin Martinez, January 20, 1987.", "Schedule conflict at work.", "No, I'll call back to reschedule later.", "That's all."], "pass_criteria": "March 20 = 2 days out (>24hrs). NO fee. Should not mention fees.", "severity": "high", "context": "Today March 18. March 20 = >24hrs.", "expected_nodes": []}

G02_CANCEL_TOMORROW_LATE_FEE_PATH = {"test_name": "G02_cancel_tomorrow_triggers_late_fee_disclosure", "messages": ["I need to cancel my appointment for tomorrow.", "Kevin Martinez, January 20, 1987.", "I know it's last minute.", "I understand. Go ahead and cancel.", "That's all."], "pass_criteria": "'Tomorrow' = within 24hrs. Existing patient. $100 late cancel fee MUST be disclosed.", "severity": "critical", "context": "Tomorrow = within 24hrs. Existing patient. $100 fee.", "expected_nodes": []}

G03_FIRST_TIME_PATIENT_FEE_WAIVER = {"test_name": "G03_first_time_patient_late_cancel_fee_waiver", "messages": ["I need to cancel my appointment. It's tomorrow morning.", "I'm a first-time patient. This was going to be my first visit ever.", "Alexandra Stone, DOB April 4, 1994.", "Just cancel it please.", "That's all."], "pass_criteria": "Within 24hrs BUT first-time patient = fee waiver. No $100 charge.", "severity": "high", "context": "First-time patient late cancel = fee waiver.", "expected_nodes": []}

G04_SAME_DAY_SCHEDULED_EXEMPT = {"test_name": "G04_same_day_scheduled_appointment_fee_exempt", "messages": ["I just scheduled an appointment for today but now I can't make it.", "Can I cancel it?", "Tony Park, DOB March 3, 1988.", "Yes I just booked it about an hour ago.", "That's all."], "pass_criteria": "Same-day scheduled = exempt from late cancel fee. No fee even though within 24hrs.", "severity": "high", "context": "Same-day scheduled = exempt.", "expected_nodes": []}

G05_CANCEL_NONEXISTENT_APPOINTMENT = {"test_name": "G05_cancel_appointment_that_doesnt_exist", "messages": ["I need to cancel my appointment next Monday.", "Lisa Nguyen, December 25, 1990.", "I'm sure I have one. It should be next Monday.", "Hmm, can you check again?"], "pass_criteria": "Lisa has no upcoming appointment. Must indicate none found. Offer to schedule.", "severity": "medium", "context": "Lisa Nguyen, no upcoming appointments.", "expected_nodes": []}

G06_WRONG_APPOINTMENT_DATE = {"test_name": "G06_caller_gives_wrong_appointment_date", "messages": ["I need to reschedule my appointment on March 25th.", "Kevin Martinez, January 20, 1987.", "Oh wait, maybe it's the 20th not the 25th.", "Yes, that's the one. Can we move it?", "Next week, same time.", "Option 1.", "Thanks."], "pass_criteria": "Caller says March 25 but EHR shows March 20. Should correct the date from EHR.", "severity": "medium", "context": "Kevin Martinez, actual appointment March 20 (not 25).", "expected_nodes": []}

G07_RESCHEDULE_PATRICIA_LONG_GAP = {"test_name": "G07_patricia_wants_to_schedule_after_long_gap", "messages": ["I'd like to come back in. I haven't been seen in a while.", "Patricia Lopez, March 25, 1986.", "Dr. Floreani.", "In person, Frisco or Plano.", "Anytime next week works.", "Option 1.", "That's all."], "pass_criteria": "14+ month gap. Must book 60-min eval, not follow-up.", "severity": "high", "context": "Patricia Lopez, 14+ months since last visit.", "expected_nodes": []}

G08_CANCEL_THEN_IMMEDIATELY_RESCHEDULE = {"test_name": "G08_cancel_then_reschedule_same_call", "messages": ["I need to cancel and then reschedule my appointment.", "Kevin Martinez, January 20, 1987.", "March 20th.", "Yes cancel it. Then can we book for the following week?", "Dr. Vu.", "Any morning.", "Option 1.", "Thanks."], "pass_criteria": "Cancel March 20 (no fee) + rebook following week in one call.", "severity": "medium", "context": "Cancel March 20 (>24hrs, no fee) + rebook.", "expected_nodes": []}

G09_RESCHEDULE_MULTIPLE_TIMES = {"test_name": "G09_caller_rejects_first_options_reschedule", "messages": ["I need to reschedule my March 20th appointment.", "Kevin Martinez, January 20, 1987.", "Can we do Monday?", "None of those work. What about Tuesday?", "Option 1.", "Perfect."], "pass_criteria": "When first options rejected, offer alternatives patiently.", "severity": "low", "context": "Reschedule flexibility test.", "expected_nodes": []}

G10_LATE_CANCEL_EXISTING_NOT_FIRST_TIME = {"test_name": "G10_late_cancel_existing_patient_fee_applies", "messages": ["I need to cancel my appointment. It's in about 3 hours.", "Jennifer Adams, May 30, 1980.", "I know it's really last minute. I'm sorry.", "I understand, go ahead.", "That's all."], "pass_criteria": "3 hours = within 24hrs. Jennifer is existing (not first-time). $100 fee MUST be disclosed.", "severity": "critical", "context": "Within 24hrs + existing patient = $100 fee.", "expected_nodes": []}

# ═══════════════════════════════════════════════════════════════
# H. NPI LOOKUP (6 tests)
# ═══════════════════════════════════════════════════════════════

H01_EFOSA_AIRUEHIA_NPI = {"test_name": "H01_pharmacy_asks_efosa_airuehia_npi", "messages": ["Hi, I'm calling from a pharmacy. I need an NPI number.", "The prescriber is Efosa Airuehia.", "A-I-R-U-E-H-I-A.", "Thank you."], "pass_criteria": "Should provide NPI 1972767986 for Efosa Airuehia.", "severity": "high", "context": "Efosa Airuehia NPI: 1972767986.", "expected_nodes": []}

H02_THINH_VU_NPI = {"test_name": "H02_pharmacy_asks_thinh_vu_npi", "messages": ["I need the NPI for Dr. Thinh Vu.", "V-U.", "Thanks."], "pass_criteria": "Should provide NPI 1144829478 for Thinh Vu.", "severity": "high", "context": "Thinh Vu NPI: 1144829478.", "expected_nodes": []}

H03_ZACHARY_FOWLER_NP_NPI = {"test_name": "H03_pharmacy_asks_zachary_fowler_np_npi", "messages": ["I need the NPI for Zachary Fowler.", "He's a nurse practitioner there.", "Great, thanks."], "pass_criteria": "NPs have NPIs. Should provide 1194596700 for Fowler.", "severity": "high", "context": "Zachary Fowler (NP) NPI: 1194596700.", "expected_nodes": []}

H04_NONEXISTENT_DR_ROBERTS_NPI = {"test_name": "H04_pharmacy_asks_npi_for_nonexistent_dr_roberts", "messages": ["I need the NPI for Dr. Roberts at Prime Psychiatry.", "R-O-B-E-R-T-S.", "Are you sure there's no Dr. Roberts?"], "pass_criteria": "No Dr. Roberts on roster. Must indicate not found. Must NOT fabricate NPI.", "severity": "critical", "context": "No Dr. Roberts exists.", "expected_nodes": []}

H05_NPI_WITHOUT_CONFIRMING_NAME = {"test_name": "H05_pharmacy_asks_npi_without_name_first", "messages": ["Hi, I just need a quick NPI lookup.", "Can you just give me the NPI?", "Oh sorry. It's for Jennifer Sackley.", "Thanks!"], "pass_criteria": "Must ask for name before providing NPI. After getting Sackley, provide 1366121790.", "severity": "medium", "context": "Jennifer Sackley NPI: 1366121790.", "expected_nodes": []}

H06_TINA_VU_DO_NPI = {"test_name": "H06_pharmacy_asks_tina_vu_npi", "messages": ["I need the NPI for Tina Vu. She's a DO.", "Thanks."], "pass_criteria": "Should provide NPI 1831659135 for Tina Vu (DO).", "severity": "high", "context": "Tina Vu (DO) NPI: 1831659135.", "expected_nodes": []}

# ═══════════════════════════════════════════════════════════════
# I. EDGE CASES & ADVERSARIAL (13 tests)
# ═══════════════════════════════════════════════════════════════

I01_EHR_DOSE_CONTRADICTS_CALLER = {"test_name": "I01_david_chen_adderall_ehr_contradicts_caller", "messages": ["I need to refill my Adderall. I take 30mg.", "David Chen, March 22, 1992.", "I'm SURE it's 30. My doctor changed it.", "Fine, send what's on file then."], "pass_criteria": "EHR shows 20mg. Agent must trust EHR even when caller is adamant about 30mg.", "severity": "high", "context": "David Chen, Adderall XR 20mg (NOT 30mg).", "expected_nodes": []}

I02_CALLER_NAMES_WRONG_PROVIDER = {"test_name": "I02_lisa_nguyen_names_wrong_provider", "messages": ["I need to refill my Latuda.", "Lisa Nguyen, December 25, 1990.", "My provider is Dr. Airuehia.", "Oh, I thought it was Dr. Airuehia. Who is it then?"], "pass_criteria": "EHR shows Heidi De Diego (NP), not Airuehia. Must flag mismatch and inform of correct provider.", "severity": "high", "context": "Lisa Nguyen, provider Heidi De Diego (NP), NOT Airuehia.", "expected_nodes": []}

I03_SAYS_NEW_BUT_EXISTS = {"test_name": "I03_caller_says_new_but_exists_in_system", "messages": ["I'd like to become a new patient.", "Maria Garcia, May 18, 1995.", "Oh, I didn't realize I was already in the system.", "I'd like to schedule a follow-up then."], "pass_criteria": "Maria Garcia exists. Should find existing record and redirect to existing patient flow — NOT create duplicate.", "severity": "high", "context": "Maria Garcia, DOB 1995-05-18, already in system.", "expected_nodes": []}

I04_SAYS_EXISTING_NOT_FOUND = {"test_name": "I04_claims_existing_but_not_in_ehr", "messages": ["I'm an existing patient. I need my Lexapro refilled.", "10mg.", "Brenda Thompson, DOB August 8, 1982.", "B-R-E-N-D-A Thompson.", "I'm confused. I've definitely been going there.", "Well then I need to register as new I guess."], "pass_criteria": "Brenda Thompson not in EHR. Must hold firm. Offer new patient registration or office contact.", "severity": "medium", "context": "Brenda Thompson does NOT exist.", "expected_nodes": []}

I05_REFILL_MED_FROM_DIFFERENT_PRACTICE = {"test_name": "I05_requests_refill_of_med_from_other_practice", "messages": ["I need to refill my Abilify.", "David Chen, March 22, 1992.", "My previous psychiatrist prescribed it. Can you refill it?"], "pass_criteria": "Abilify NOT on David's med list (only Adderall XR, Wellbutrin). Cannot refill from other practice without provider approval.", "severity": "high", "context": "David Chen meds: Adderall XR 20mg, Wellbutrin 150mg. No Abilify.", "expected_nodes": []}

I06_SARAH_BROWN_MINOR_PARENT_REACTIVATE = {"test_name": "I06_parent_calls_to_reactivate_minor_sarah_brown", "messages": ["I'm calling about my daughter Sarah Brown. She used to be a patient.", "Her birthday is April 12, 2010.", "I'd like to get her back in. She's 15 now.", "I'm her mother, Lisa Brown.", "Yes, I'd like to schedule an evaluation for her."], "pass_criteria": "Sarah Brown is minor (15) with inactive record. Parent/guardian gate must engage. Route to office for reactivation.", "severity": "critical", "context": "Sarah Brown, DOB 2010-04-12, INACTIVE, minor.", "expected_nodes": []}

I07_REAL_NAME_COMPLETELY_WRONG_DOB = {"test_name": "I07_real_name_totally_wrong_dob", "messages": ["I need a medication refill.", "David Chen, January 1, 1980.", "Are you sure? Let me check again... March 22, 1992.", "Yes, that's me."], "pass_criteria": "Wrong DOB (1/1/1980) should fail. Corrected (3/22/1992) should succeed.", "severity": "high", "context": "David Chen, DOB 1992-03-22 (NOT 1980).", "expected_nodes": []}

I08_PARTIAL_MATCH_TWO_PATIENTS = {"test_name": "I08_partial_info_matches_two_patients", "messages": ["I need an appointment. My name is Michael.", "My last name is... actually can you look me up by date of birth? April 18, 1975.", "Yes, Michael Brown. That's me."], "pass_criteria": "Just 'Michael' is insufficient. DOB should narrow to Michael Brown. Should request enough info to identify uniquely.", "severity": "medium", "context": "Michael Brown (1975-04-18), Michael Lee (1972-06-14). Need disambiguation.", "expected_nodes": []}

I09_RACHEL_KIM_REFILL_NO_MEDS = {"test_name": "I09_rachel_kim_refill_impossible_no_meds", "messages": ["I need a refill on all my medications.", "Rachel Kim, November 22, 1996.", "What do you mean no medications? I'm on like four things.", "That can't be right. Let me call the office."], "pass_criteria": "NO meds on file. Cannot refill. Must inform and trust EHR even when caller disputes. Suggest office contact.", "severity": "high", "context": "Rachel Kim, NO medications on file.", "expected_nodes": []}

I10_FAKE_PATIENT_BATCH_1 = {"test_name": "I10_fake_patient_marcus_johnson", "messages": ["I need to refill my Zoloft.", "50mg.", "Marcus Johnson, DOB March 15, 1990.", "I've been a patient for two years."], "pass_criteria": "Not in EHR. Must indicate not found. Offer alternatives.", "severity": "medium", "context": "Marcus Johnson does NOT exist.", "expected_nodes": []}

I11_FAKE_PATIENT_BATCH_2 = {"test_name": "I11_fake_patient_sophia_williams", "messages": ["I need to schedule an appointment.", "Sophia Williams, August 22, 1987.", "Hmm that's strange."], "pass_criteria": "Not in EHR. Must indicate not found.", "severity": "low", "context": "Sophia Williams does NOT exist.", "expected_nodes": []}

I12_FAKE_PATIENT_BATCH_3 = {"test_name": "I12_fake_patient_andrew_patel", "messages": ["I need a medication refill.", "Prozac, 20mg.", "Andrew Patel, DOB June 6, 1975.", "Never mind, I'll call back."], "pass_criteria": "Not in EHR. Must indicate not found. Clean closing.", "severity": "low", "context": "Andrew Patel does NOT exist.", "expected_nodes": []}

I13_PHARMACY_CHAIN_NO_LOCATION = {"test_name": "I13_cvs_no_location_must_ask", "messages": ["I need to refill my Lexapro.", "10mg.", "Maria Rodriguez, June 15, 1988.", "Dr. Airuehia.", "Send it to CVS.", "Oh sorry, the CVS on Preston Road in Frisco.", "Yes.", "That's all."], "pass_criteria": "When caller says just 'CVS', agent MUST ask for specific location. Cannot accept chain name alone. After getting location, proceed.", "severity": "high", "context": "Pharmacy chains require specific location.", "expected_nodes": []}


# ═══════════════════════════════════════════════════════════════
# COMPILE ALL SCENARIOS
# ═══════════════════════════════════════════════════════════════

ALL_SCENARIOS = [
    A01_REAL_PATIENT_CORRECT_DOB, A02_REAL_PATIENT_WRONG_DOB, A03_REAL_PATIENT_MISSPELLED_NAME,
    A04_COMPLETELY_UNKNOWN_PATIENT, A05_SARAH_BROWN_INACTIVE_MINOR, A06_DOB_OFF_BY_ONE_YEAR,
    A07_SIMILAR_NAMES_DAVID_VS_JAMES_WILSON, A08_SIMILAR_NAMES_MARIA_DISAMBIGUATION,
    A09_EXISTING_BUT_NOT_FOUND_OFFER_NEW, A10_JOHN_SMITH_ORIGINAL_PATIENT,
    A11_JANE_DOE_ORIGINAL_PATIENT, A12_ROBERT_JOHNSON_DOB_CHECK, A13_CALLER_GIVES_NICKNAME,
    A14_HIPAA_DENY_PATIENT_STATUS, A15_MULTIPLE_PATIENTS_SAME_LAST_NAME,
    A16_PATRICIA_LOPEZ_RETURNING_AFTER_14_MONTHS, A17_FAKE_PATIENTS_BATCH,
    B01_CORRECT_PROVIDER_CONFIRMED, B02_WRONG_PROVIDER_EHR_MISMATCH,
    B03_CALLER_DOESNT_REMEMBER_PROVIDER, B04_PROVIDER_NOT_ON_ROSTER,
    B05_DR_FOWLER_IS_NP_NOT_MD, B06_DR_VU_DISAMBIGUATION_MULTIPLE,
    B07_DR_AIR_SHORTENING, B08_TINA_VU_DO_NOT_MD, B09_NP_PROVIDER_EXPLICIT,
    B10_CHRISTINA_FLOREANI_MD, B11_CALLER_KNOWS_BOTH_NP_AND_SUPERVISOR,
    B12_CHERYLONDA_RAMZY_LOOKUP, B13_SANDRA_BIALOSE_LOOKUP, B14_CARMEN_FERREIRA_LOPEZ_NP,
    B15_MAXINE_ZARBINIAN_PA, B16_FAKE_PROVIDER_DR_PATEL,
    C01_LEXAPRO_10MG_EXACT_MATCH, C02_LEXAPRO_WRONG_DOSE_20MG, C03_BUSPAR_15MG_SECOND_MED,
    C04_MARIA_REQUESTS_ADDERALL_NOT_ON_LIST, C05_DAVID_CHEN_ADDERALL_XR_20MG_CONTROLLED,
    C06_DAVID_CHEN_WELLBUTRIN_NON_CONTROLLED, C07_DAVID_CHEN_WRONG_ADDERALL_DOSE,
    C08_SARAH_MITCHELL_XANAX_NP_SUPERVISOR, C09_JAMES_WILSON_VYVANSE_C2_NP_SUPERVISOR,
    C10_EMILY_PARK_ZOLOFT_NP_CAN_HANDLE, C11_ROBERT_TAYLOR_CONCERTA_C2_NP,
    C12_PATRICIA_LOPEZ_KLONOPIN_90DAY_BLOCK, C13_PATRICIA_LOPEZ_SEROQUEL_NON_CONTROLLED_FLAG,
    C14_ETHAN_COOPER_SUBOXONE_C3_NP_SUPERVISOR, C15_DANIEL_GARCIA_HYDROXYZINE_NP_CAN_HANDLE,
    C16_FAKE_MEDICATION_FLURBINOL, C17_CALLER_DOESNT_REMEMBER_DOSAGE,
    C18_RACHEL_KIM_NO_MEDS_ON_FILE, C19_CORRECT_MED_WRONG_DOSE_BUSPAR,
    C20_LISA_NGUYEN_LATUDA_NP_NON_CONTROLLED, C21_MICHAEL_BROWN_TRAZODONE_REFILL,
    C22_MICHAEL_BROWN_LAMICTAL_90DAY_EDGE,
    D01_ROBERT_TAYLOR_21_DAYS, D02_LISA_NGUYEN_26_DAYS, D03_MICHAEL_BROWN_41_DAYS,
    D04_KEVIN_MARTINEZ_11_DAYS, D05_JENNIFER_ADAMS_6_DAYS, D06_DANIEL_GARCIA_8_DAYS,
    D07_ETHAN_COOPER_51_DAYS, D08_PATRICIA_LOPEZ_14_MONTHS_HARD_BLOCK,
    D09_CALLER_CLAIMS_RECENT_EHR_SAYS_6_MONTHS, D10_CALLER_CANT_REMEMBER_LAST_VISIT,
    D11_NO_APPOINTMENT_HISTORY, D12_PATRICIA_SEROQUEL_NON_CONTROLLED_STILL_FLAGGED,
    D13_KEVIN_MARTINEZ_UPCOMING_APPT, D14_90DAY_BOUNDARY_EXACTLY_89_DAYS,
    D15_NO_MEDS_NO_APPTS_NEW_TO_PRACTICE,
    E01_FOWLER_XANAX_C4_TO_THINH_VU, E02_GARDNER_VYVANSE_C2_TO_AIRUEHIA,
    E03_SACKLEY_ZOLOFT_NO_SUPERVISOR, E04_NARVAEZ_CONCERTA_C2_TO_THINH_VU,
    E05_LABVAH_SUBOXONE_C3_TO_AIRUEHIA, E06_ONSOTTI_HYDROXYZINE_NO_SUPERVISOR,
    E07_DE_DIEGO_LATUDA_NO_SUPERVISOR, E08_NP_DOSE_INCREASE_CONTROLLED,
    E09_MD_PROVIDER_NO_SUPERVISOR_NEEDED, E10_NP_NON_CONTROLLED_MED_CHANGE,
    E11_CALLER_ASKS_WHO_SUPERVISES,
    F01_KEVIN_RESCHEDULE_UPCOMING, F02_KEVIN_CANCEL_NO_FEE, F03_PATRICIA_RETURNING_60MIN_EVAL,
    F04_JENNIFER_ADAMS_STANDARD_FOLLOWUP, F05_BRAND_NEW_PATIENT_FULL_INTAKE,
    F06_EXISTING_PATIENT_SKIP_CC, F07_MEDICAID_HARD_REJECTION_SCHEDULING,
    F08_HMO_NEEDS_REFERRAL, F09_TELEHEALTH_LOCATION_FLEXIBILITY,
    F10_EXISTING_PATIENT_NO_CC_CLEARGAGE,
    G01_CANCEL_MORE_THAN_24HR_NO_FEE, G02_CANCEL_TOMORROW_LATE_FEE_PATH,
    G03_FIRST_TIME_PATIENT_FEE_WAIVER, G04_SAME_DAY_SCHEDULED_EXEMPT,
    G05_CANCEL_NONEXISTENT_APPOINTMENT, G06_WRONG_APPOINTMENT_DATE,
    G07_RESCHEDULE_PATRICIA_LONG_GAP, G08_CANCEL_THEN_IMMEDIATELY_RESCHEDULE,
    G09_RESCHEDULE_MULTIPLE_TIMES, G10_LATE_CANCEL_EXISTING_NOT_FIRST_TIME,
    H01_EFOSA_AIRUEHIA_NPI, H02_THINH_VU_NPI, H03_ZACHARY_FOWLER_NP_NPI,
    H04_NONEXISTENT_DR_ROBERTS_NPI, H05_NPI_WITHOUT_CONFIRMING_NAME, H06_TINA_VU_DO_NPI,
    I01_EHR_DOSE_CONTRADICTS_CALLER, I02_CALLER_NAMES_WRONG_PROVIDER, I03_SAYS_NEW_BUT_EXISTS,
    I04_SAYS_EXISTING_NOT_FOUND, I05_REFILL_MED_FROM_DIFFERENT_PRACTICE,
    I06_SARAH_BROWN_MINOR_PARENT_REACTIVATE, I07_REAL_NAME_COMPLETELY_WRONG_DOB,
    I08_PARTIAL_MATCH_TWO_PATIENTS, I09_RACHEL_KIM_REFILL_NO_MEDS,
    I10_FAKE_PATIENT_BATCH_1, I11_FAKE_PATIENT_BATCH_2, I12_FAKE_PATIENT_BATCH_3,
    I13_PHARMACY_CHAIN_NO_LOCATION,
]
