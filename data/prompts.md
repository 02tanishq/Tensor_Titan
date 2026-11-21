# Data Generation Prompts & Provenance Kit
**Fictional Operator:** Ujjwal Rail  
**Target Event:** HCLTech Future Ready AI Engineer Hackathon  
**Model Used:** Gemini 3.8 Flash (Google DeepMind)  
**Generation Date:** 2026-11-21  

---

## 1. System Prompt Used for Data Generation
```text
You are a Lead Railway Systems Domain Architect and Data Engineer building synthetic, high-fidelity travel data for "Ujjwal Rail", a fictional Indian passenger train operator. 
You must generate realistic relational data, official policy manuals, revised circulars, and FAQs adhering to strict relational consistency, temporal validity, and awkward edge cases.
Never use real passenger PII, phone numbers, or real IRCTC ticket references. All numbers, stations, train names, and policies must be internally consistent.
```

---

## 2. Word-for-Word Prompt: Rules, Circulars & FAQs (Section 4.1)

```text
Generate a comprehensive policy and rules dataset for fictional train operator "Ujjwal Rail" conforming to the following structure:

1. Exactly 12 official rules documents:
   - RUL-BKG-01: General Booking and Reservation Guidelines (ARP 120 days, max 6 pax standard / 4 Tatkal, booking hours 00:30 to 23:45).
   - RUL-CLS-01: Travel Classes (1AC, 2AC, 3AC, CC, SL, 2S, berth dimensions, bedroll amenities).
   - RUL-CAN-01: Ticket Cancellation & Refund Policy with strict refund cut-off table:
     * > 48 hours: Flat cancellation fee (1AC: Rs 240, 2AC: Rs 180, 3AC: Rs 150, SL: Rs 100, 2S: Rs 50).
     * 48h to 12h: 25% of fare subject to class minimum.
     * 12h to 4h: 50% of fare subject to class minimum.
     * < 4h: No refund on confirmed tickets.
   - RUL-WL-01: Waitlist (WL) and Reservation Against Cancellation (RAC) rules, auto-cancellation of fully waitlisted e-tickets upon charting, partial waitlist handling.
   - RUL-TAT-01: Tatkal scheme (10 AM AC, 11 AM Non-AC, 10% 2S / 30% others, no refund on confirmed Tatkal).
   - RUL-ID-01: Prescribed original ID proofs (Aadhaar, Voter ID, Passport, DL, PAN, Student ID, DigiLocker).
   - RUL-LUG-01: Free luggage allowances and pet dog carriage (pet dogs strictly restricted to 1AC full coupe/cabin booking; prohibited in 2AC, 3AC, SL).
   - RUL-CON-01: Concessions (Divyangjan, medical patients, suspended general senior citizen discount).
   - RUL-BRD-01: Change of boarding station (up to 4 hours before originating departure, allowed once).
   - RUL-DIS-01: Disruption, train cancellation (100% automatic refund) and >3 hr late train refunds via TDR.
   - RUL-CMP-01: Grievance redressal, harassment, security emergencies escalation matrix.
   - RUL-BRK-01: Break of journey rules (>500 km, max 2 days).

2. Exactly 6 official circulars:
   - At least 2 modifying earlier rules:
     * CIR-2026-01: Revising flat cancellation charges for 2AC (Rs 180 -> Rs 200) and 3AC (Rs 150 -> Rs 180) effective 2026-02-01.
     * CIR-2026-02: Revising minimum Tatkal charges for SL (Rs 100 -> Rs 150) and 3AC (Rs 250 -> Rs 300) effective 2026-04-01.
   - At least 1 taking effect on a future date:
     * CIR-2026-05: Peak holiday season cancellation cut-off window extension to 72 hours, effective 2026-12-01.
   - CIR-2026-03: Winter festival special trains schedule notification (02125/02126).
   - CIR-2026-04: Child ticket fare & separate berth policy revision (Bilingual Hindi/English).
   - CIR-2026-06: Mandatory handheld digital terminal verification by TTEs.

3. Exactly 20 FAQs or past helpdesk replies:
   - At least 2 outdated due to subsequent circulars (FAQ-004 on 2AC cancellation fee claiming Rs 180 instead of Rs 200, FAQ-009 on Tatkal SL fee claiming Rs 100 instead of Rs 150).
   - At least 7 in Hindi or mixed Hindi-English (Hinglish) covering pet policies, cancellation, boarding deadlines, and late train refunds.

4. A settings key-value table:
   Holding numerical parameters (cancellation charges, cut-off percentages, Tatkal minimums, action TTL=10 mins) with their respective source document references.
```

---

## 3. Word-for-Word Prompt: Relational Operational Data (Section 4.2)

```text
Generate SQLite operational tables for Ujjwal Rail strictly matching the requested schema:

- 15 Stations (PUNE, CSMT, BCT, KYN, BSL, NGP, SUR, BPL, NDLS, DDU, GKP, ADI, HWH, MAO, JAT) with city and station aliases.
  * Must include ambiguous station names: CSMT (Chhatrapati Shivaji Maharaj Terminus) and BCT (Mumbai Central) both in Mumbai.
- 25 Trains with operating days, classes, and detailed intermediate stops with arrival/departure and day_offset.
  * Must include awkward midnight departure: Train 12124 (Midnight Deccan Special) departing at 00:25 from Pune.
- Fares table mapping train numbers, classes, and station pairs.
- Seat availability table covering 14 consecutive days for all running trains, with realistic states: available seats, RAC, waitlist, and fully booked.
- 25 Passengers with diverse home cities, preferred languages (en, hi, mr, gu), and masked 4-digit phones.
  * Must include awkward case: Passenger PASS-025 with zero bookings.
- 51 Bookings distributed across all required statuses: CONFIRMED, RAC, WL, CANCELLED, OPERATOR_CANCELLED.
  * Include awkward case: UR-30418 cancelled exactly at 48 hours prior to departure.
  * Include awkward case: UR-30419 cancelled 1 minute past the 48-hr cut-off (47 hours 59 minutes).
  * Include awkward case: UR-50012 with 2 passengers where one is CNF and one is WL.
- booking_travellers table with coach and berth assignments.
- actions table tracking Level 1 pending/executed actions with TTL expiry.
```
