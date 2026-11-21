"""
Ujjwal Rail Comprehensive Dataset Generator
Compliant with HCLTech Future Ready AI Engineer Hackathon:
Section 4.1, Section 4.2, Section 5, Section 6, and Section 8.
"""

import sqlite3
import json
import os
import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(CURRENT_DIR, "ujjwal_rail.db")

def init_db(cursor):
    cursor.executescript("""
    DROP TABLE IF EXISTS stations;
    DROP TABLE IF EXISTS trains;
    DROP TABLE IF EXISTS train_stops;
    DROP TABLE IF EXISTS fares;
    DROP TABLE IF EXISTS seats;
    DROP TABLE IF EXISTS passengers;
    DROP TABLE IF EXISTS bookings;
    DROP TABLE IF EXISTS booking_travellers;
    DROP TABLE IF EXISTS actions;
    DROP TABLE IF EXISTS settings;
    DROP TABLE IF EXISTS rules;
    DROP TABLE IF EXISTS circulars;
    DROP TABLE IF EXISTS faqs;
    DROP TABLE IF EXISTS audit_logs;

    CREATE TABLE stations (
        station_code TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        other_names TEXT,
        city TEXT NOT NULL
    );

    CREATE TABLE trains (
        train_no TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        runs_on TEXT NOT NULL,
        classes TEXT NOT NULL
    );

    CREATE TABLE train_stops (
        train_no TEXT,
        station_code TEXT,
        stop_order INTEGER,
        arrival TEXT,
        departure TEXT,
        day_offset INTEGER,
        PRIMARY KEY (train_no, station_code)
    );

    CREATE TABLE fares (
        train_no TEXT,
        class TEXT,
        from_code TEXT,
        to_code TEXT,
        fare REAL,
        PRIMARY KEY (train_no, class, from_code, to_code)
    );

    CREATE TABLE seats (
        train_no TEXT,
        journey_date TEXT,
        class TEXT,
        available INTEGER,
        rac INTEGER,
        waitlist INTEGER,
        PRIMARY KEY (train_no, journey_date, class)
    );

    CREATE TABLE passengers (
        passenger_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        phone_last4 TEXT NOT NULL,
        preferred_language TEXT NOT NULL
    );

    CREATE TABLE bookings (
        booking_id TEXT PRIMARY KEY,
        passenger_id TEXT NOT NULL,
        train_no TEXT NOT NULL,
        journey_date TEXT NOT NULL,
        from_code TEXT NOT NULL,
        to_code TEXT NOT NULL,
        class TEXT NOT NULL,
        amount_paid REAL NOT NULL,
        status TEXT NOT NULL,
        booked_at TEXT NOT NULL,
        FOREIGN KEY (passenger_id) REFERENCES passengers(passenger_id),
        FOREIGN KEY (train_no) REFERENCES trains(train_no)
    );

    CREATE TABLE booking_travellers (
        booking_id TEXT,
        traveller_name TEXT,
        age INTEGER,
        status TEXT,
        coach TEXT,
        berth TEXT,
        PRIMARY KEY (booking_id, traveller_name),
        FOREIGN KEY (booking_id) REFERENCES bookings(booking_id)
    );

    CREATE TABLE actions (
        action_id TEXT PRIMARY KEY,
        passenger_id TEXT NOT NULL,
        booking_id TEXT,
        action_type TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        result TEXT
    );

    CREATE TABLE settings (
        name TEXT PRIMARY KEY,
        value REAL NOT NULL,
        source_doc TEXT NOT NULL
    );

    CREATE TABLE rules (
        doc_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        effective_date TEXT NOT NULL,
        content TEXT NOT NULL
    );

    CREATE TABLE circulars (
        doc_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        issue_date TEXT NOT NULL,
        effective_date TEXT NOT NULL,
        modifies_rule TEXT,
        content TEXT NOT NULL,
        language TEXT DEFAULT 'en'
    );

    CREATE TABLE faqs (
        faq_id TEXT PRIMARY KEY,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        category TEXT NOT NULL,
        language TEXT DEFAULT 'en',
        is_outdated INTEGER DEFAULT 0,
        superseded_by TEXT
    );

    CREATE TABLE audit_logs (
        trace_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        passenger_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        user_query TEXT NOT NULL,
        answer_type TEXT NOT NULL,
        answer_text TEXT NOT NULL,
        sources_cited TEXT,
        tools_used TEXT,
        pending_action TEXT,
        handed_to_human TEXT
    );
    """)

def populate_rules_and_circulars(cursor):
    rules = [
        ("RUL-BKG-01", "General Booking and Reservation Guidelines", "Booking", "2025-01-01",
         "Section 1. Advance Reservation Period (ARP): Tickets can be booked up to 120 days in advance (excluding the date of journey). "
         "Section 2. Maximum Passengers: A maximum of 6 passengers can be booked on a single standard ticket, and 4 passengers on a Tatkal ticket. "
         "Section 3. Booking Window: Online booking is open from 00:30 hrs to 23:45 hrs daily. Maintenance window operates between 23:45 hrs and 00:30 hrs."),

        ("RUL-CLS-01", "Travel Classes and Accommodation Types", "Classes", "2025-01-01",
         "Section 1. Classes Offered: Ujjwal Rail operates 1AC (First AC), 2AC (Two-Tier AC), 3AC (Three-Tier AC), CC (AC Chair Car), SL (Sleeper Class), and 2S (Second Sitting). "
         "Section 2. Berth Dimensions and Bedrolls: Complimentary bedrolls are provided in 1AC, 2AC, and 3AC. Sleeper class passengers may rent bedrolls on select routes subject to prior notification."),

        ("RUL-CAN-01", "Ticket Cancellation and Refund Policy", "Cancellation", "2025-01-01",
         "Section 1. Cut-off Tiers: "
         "(a) More than 48 hours before scheduled train departure: Flat cancellation deduction per passenger: 1AC=Rs 240, 2AC=Rs 180, 3AC=Rs 150, SL=Rs 100, 2S=Rs 50. "
         "(b) Between 48 hours and up to 12 hours before scheduled departure: 25% of the total fare paid, subject to minimum flat cancellation fee of the class. "
         "(c) Between 12 hours and up to 4 hours before scheduled departure (or chart preparation): 50% of the total fare paid, subject to minimum flat cancellation fee. "
         "(d) Less than 4 hours before departure or after chart preparation: No refund admissible on confirmed tickets. "
         "Section 2. Computation: Cut-off time is computed strictly against the scheduled departure of the train from the ticket's booked origin station."),

        ("RUL-WL-01", "Waitlist (WL) and Reservation Against Cancellation (RAC)", "Waitlist", "2025-01-01",
         "Section 1. RAC Privileges: RAC ticket holders are guaranteed travel accommodation with a shared lower berth. If cancellations occur, RAC passengers are upgraded to confirmed berths in order of booking. "
         "Section 2. Fully Waitlisted E-Tickets: E-tickets where all passenger statuses remain Waitlisted (WL) after final chart preparation are automatically cancelled by the system, and full fare is refunded to the source account without deduction. "
         "Section 3. Partially Confirmed Tickets: If at least one passenger is CNF/RAC on a PNR while others are WL, the WL passenger may travel only if permitted by the on-board Ticket Examiner, or file a TDR up to 30 minutes before departure for a refund."),

        ("RUL-TAT-01", "Tatkal Booking Scheme and Guidelines", "Tatkal", "2025-01-01",
         "Section 1. Timings: Tatkal booking opens at 10:00 AM for AC classes (1AC, 2AC, 3AC, CC) and at 11:00 AM for Non-AC classes (SL, 2S) on the day prior to the train journey from originating station. "
         "Section 2. Charges: Tatkal charges are fixed at 10% of basic fare for Second Sitting and 30% of basic fare for all other classes, subject to a minimum of Rs 100 for SL and Rs 250 for 3AC. "
         "Section 3. Cancellation: No refund is granted on cancellation of confirmed Tatkal tickets under normal conditions."),

        ("RUL-ID-01", "Accepted Proofs of Identity for Travel", "Identity", "2025-01-01",
         "Section 1. Mandatory ID: At least one passenger booked on a ticket must carry an original valid identity card during the journey. "
         "Section 2. Prescribed Documents: Accepted IDs include: (1) Aadhaar Card (physical or m-Aadhaar), (2) Voter Photo Identity Card, (3) Passport, (4) Driving Licence, (5) Pan Card, (6) Central/State Govt. Employee ID, (7) Student ID issued by recognized institutions, (8) Nationalised Bank Passbook with photograph."),

        ("RUL-LUG-01", "Luggage Allowances and Pet Transportation", "Luggage", "2025-01-01",
         "Section 1. Free Baggage Allowance: 1AC: 70 kg, 2AC: 50 kg, 3AC/CC: 40 kg, SL: 40 kg, 2S: 35 kg. Marginal allowance of 10 kg permitted. "
         "Section 2. Pet Dogs Carriage: Dogs can only be carried in 1AC (First AC) coaches provided the passenger books the entire two-berth coupe or four-berth cabin. Dogs are strictly prohibited in 2AC, 3AC, CC, SL, and 2S coaches. Breaches will incur penalty of 6 times the luggage rate."),

        ("RUL-CON-01", "Concession Rules and Senior Citizen Entitlements", "Concessions", "2025-01-01",
         "Section 1. Eligibility: Concessions are available to Divyangjan (orthopaedically handicapped, visually impaired, hearing impaired), cancer patients, and accredited journalists upon verification of prescribed medical certificates. "
         "Section 2. Senior Citizens: General senior citizen concessions remain suspended; only verified medical concessions apply. Valid certificate must be presented during ticket issuance."),

        ("RUL-BRD-01", "Change of Boarding Station Guidelines", "Boarding", "2025-01-01",
         "Section 1. Permissible Timeframe: Passengers can change their boarding station online up to 4 hours prior to the scheduled departure of the train from its originating station (or before first chart preparation, whichever is earlier). "
         "Section 2. Conditions: Boarding station can be changed only once per booking. Once changed, the passenger forfeits the right to board at the original station."),

        ("RUL-DIS-01", "Disruption, Train Cancellation and Delay Refunds", "Refunds", "2025-01-01",
         "Section 1. Train Cancelled by Operator: If a train is cancelled by Ujjwal Rail due to technical, natural, or operational reasons, a 100% full refund of the ticket amount is automatically processed without any cancellation charge. "
         "Section 2. Train Delayed by over 3 Hours: If the train is delayed at the passenger's boarding station by more than 3 hours and the passenger elects not to travel, a full refund is admissible provided a Ticket Deposit Receipt (TDR) is filed before actual train departure."),

        ("RUL-CMP-01", "Complaints, Grievances and Harassment Reporting", "Complaints", "2025-01-01",
         "Section 1. Grievance Redressal: General complaints regarding catering, cleanliness, or refund discrepancies must be logged via Helpdesk ticket. "
         "Section 2. Safety and Security Emergency: Reports of theft, assault, harassment of women passengers, or medical emergencies must be escalated immediately to the Rail Security Control Room with Train Number, Coach, and Berth details."),

        ("RUL-BRK-01", "Break of Journey and Intermediate Transit Rules", "Transit", "2025-01-01",
         "Section 1. Eligibility: Break of journey is permitted only on tickets covering a distance of more than 500 km. The first break of journey is permissible only after completing 500 km of travel. "
         "Section 2. Duration: Break of journey is allowed for a maximum of 2 days per break, excluding day of arrival and departure.")
    ]
    cursor.executemany("INSERT INTO rules VALUES (?, ?, ?, ?, ?)", rules)

    circulars = [
        ("CIR-2026-01", "Revision of Flat Cancellation Charges for AC Classes", "2026-01-15", "2026-02-01", "RUL-CAN-01",
         "Effective 01-Feb-2026, cancellation charges for cancellations done more than 48 hours prior to train departure are revised as follows: "
         "2AC: Revised from Rs 180 to Rs 200 per passenger. "
         "3AC: Revised from Rs 150 to Rs 180 per passenger. "
         "Sleeper (SL) remains unchanged at Rs 120. First AC (1AC) remains at Rs 240. This circular supersedes RUL-CAN-01 Section 1(a).", "en"),

        ("CIR-2026-02", "Revision of Minimum Tatkal Surcharge and Distance Cap", "2026-03-10", "2026-04-01", "RUL-TAT-01",
         "Effective 01-Apr-2026, minimum Tatkal booking surcharge is revised: "
         "Sleeper class minimum charge is increased from Rs 100 to Rs 150. "
         "3AC minimum Tatkal charge is increased from Rs 250 to Rs 300. "
         "Supersedes RUL-TAT-01 Section 2.", "en"),

        ("CIR-2026-03", "Winter Festival Special Trains Schedule Notification", "2026-10-01", "2026-11-01", None,
         "To clear heavy festival passenger rush, Ujjwal Rail announces special trains 02125 (Pune to Nagpur Winter Special) "
         "and 02126 (Nagpur to Pune Winter Special) running bi-weekly with 2AC, 3AC, and Sleeper accommodation.", "en"),

        ("CIR-2026-04", "बच्चों के लिए टिकट व सीट आवंटन नीति में संशोधन", "2026-05-10", "2026-06-01", "RUL-BKG-01",
         "01 जून 2026 से प्रभावी: 5 वर्ष से 11 वर्ष तक के बच्चों के लिए यदि अलग बर्थ नहीं ली जाती है, तो मूल किराये का 50% देय होगा। "
         "यदि अलग बर्थ मांगी जाती है, तो पूरा वयस्क किराया लागू होगा। (Child ticket rule revision: half fare for child without berth, full fare with berth).", "hi"),

        ("CIR-2026-05", "Advance Revision of Holiday Cancellation Cut-Off Window (Future Date)", "2026-11-15", "2026-12-01", "RUL-CAN-01",
         "Notice is hereby given that effective from 01-Dec-2026, during peak winter holidays (Dec 15 to Jan 5), the tier-2 cancellation cut-off "
         "shall be 72 hours instead of 48 hours. Until 30-Nov-2026, standard 48 hours rule continues to apply strictly.", "en"),

        ("CIR-2026-06", "Introduction of Mandatory Handheld Terminal E-Verification", "2026-07-20", "2026-08-01", "RUL-ID-01",
         "Travelling Ticket Examiners (TTEs) are now equipped with biometric and QR code scanners. Passengers displaying m-Aadhaar or Digilocker certificates "
         "are recognized as verified digital ID proofs.", "en")
    ]
    cursor.executemany("INSERT INTO circulars VALUES (?, ?, ?, ?, ?, ?, ?)", circulars)

    faqs = [
        ("FAQ-001", "Can I carry my pet dog in 2AC or 3AC coach?",
         "No. Under rule RUL-LUG-01, dogs are strictly prohibited in 2AC, 3AC, CC, and Sleeper coaches. You may only carry your pet dog in 1AC (First AC) by booking an entire 2-berth coupe or 4-berth cabin.",
         "Luggage", "en", 0, None),

        ("FAQ-002", "What happens if my ticket is still on waitlist after chart preparation?",
         "Under rule RUL-WL-01, if your e-ticket remains fully waitlisted after final charting, the system automatically cancels it. Full refund is credited directly to your bank account without any deduction.",
         "Waitlist", "en", 0, None),

        ("FAQ-003", "Which identity cards are accepted for travel?",
         "According to RUL-ID-01, valid proofs include original Aadhaar, Voter ID, Passport, Driving Licence, Pan Card, or DigiLocker verified digital copies.",
         "Identity", "en", 0, None),

        ("FAQ-004", "What is the cancellation charge for 2AC if cancelled more than 48 hours before departure?",
         "The cancellation charge for 2AC is Rs 180 per passenger.", # OUTDATED! Superseded by CIR-2026-01 (now Rs 200)
         "Cancellation", "en", 1, "CIR-2026-01"),

        ("FAQ-005", "Can I change my boarding station after booking?",
         "Yes, as per RUL-BRD-01, you can change your boarding station online up to 4 hours before the train's scheduled departure from originating station. It can only be done once.",
         "Boarding", "en", 0, None),

        ("FAQ-006", "What is the refund if Ujjwal Rail cancels my train?",
         "Under RUL-DIS-01, if a train is cancelled by the operator, you receive a 100% full refund automatically into your payment source account without any cancellation fee deduction.",
         "Refunds", "en", 0, None),

        ("FAQ-007", "When does Tatkal booking open?",
         "Tatkal booking opens at 10:00 AM for AC classes (1AC, 2AC, 3AC, CC) and at 11:00 AM for non-AC classes (SL, 2S) one day prior to journey date from originating station (RUL-TAT-01).",
         "Tatkal", "en", 0, None),

        ("FAQ-008", "Is there any refund on confirmed Tatkal tickets?",
         "No refund is granted on cancellation of confirmed Tatkal tickets except in specific disruption circumstances like train cancellation or >3 hours delay (RUL-TAT-01).",
         "Tatkal", "en", 0, None),

        ("FAQ-009", "What is the minimum Tatkal charge for Sleeper class?",
         "The minimum Tatkal charge for Sleeper class is Rs 100.", # OUTDATED! Superseded by CIR-2026-02 (now Rs 150)
         "Tatkal", "en", 1, "CIR-2026-02"),

        ("FAQ-010", "Are senior citizens eligible for fare discount?",
         "Currently, general senior citizen concessions remain suspended under RUL-CON-01. Only verified medical patients and Divyangjan concessions are available.",
         "Concessions", "en", 0, None),

        ("FAQ-011", "How many passengers can be booked on one ticket?",
         "Under RUL-BKG-01, a maximum of 6 passengers can be booked on a general ticket, and 4 passengers on a Tatkal ticket.",
         "Booking", "en", 0, None),

        ("FAQ-012", "Can RAC passengers travel on the train?",
         "Yes, RAC (Reservation Against Cancellation) passengers are allotted a sitting berth (shared lower berth) and are permitted to board the train (RUL-WL-01).",
         "Waitlist", "en", 0, None),

        ("FAQ-013", "Kya main apne kutte (dog) ko train me le ja sakta hoon?",
         "Kutte ko sirf 1AC coach me poora coupe ya cabin book karke le जाया ja sakta hai. 2AC, 3AC ya Sleeper me pets le jana niyam RUL-LUG-01 ke tahat sakht mana hai.",
         "Luggage", "hi-en", 0, None),

        ("FAQ-014", "Kal ki train cancel karni hai, kitna paisa wapas milega?",
         "Refund train departure ke samay par depend karta hai. Agar departure me 48 se 12 ghante bache hain to 25% charge lagega. 12 se 4 ghante par 50% charge katega (RUL-CAN-01).",
         "Cancellation", "hi-en", 0, None),

        ("FAQ-015", "Waitlist ticket confirm na hone par kya hota hai?",
         "Charting ke baad agar e-ticket par sabhi yatri waitlist me rehte hain, to ticket apne aap cancel ho jata hai aur poora paisa bank account me refund ho jata hai (RUL-WL-01).",
         "Waitlist", "hi-en", 0, None),

        ("FAQ-016", "Kya train me digital Aadhaar ya DigiLocker chalega?",
         "Haan, RUL-ID-01 aur CIR-2026-06 ke anusar DigiLocker ya m-Aadhaar par dikhaya gaya ID proof poori tarah manya hai.",
         "Identity", "hi-en", 0, None),

        ("FAQ-017", "Boarding station badalne ki deadline kya hai?",
         "Aap train chhootne ke 4 ghante pehle tak online boarding station badal sakte hain. Yah suvidha keval ek baar milti hai (RUL-BRD-01).",
         "Boarding", "hi-en", 0, None),

        ("FAQ-018", "Agar train 3 ghante se zyada late ho to kya karein?",
         "Agar train 3 ghante se zyada deri se chal rahi hai, to aap departure se pehle TDR file karke bina kisi katauti ke 100% refund prapt kar sakte hain (RUL-DIS-01).",
         "Refunds", "hi-en", 0, None),

        ("FAQ-019", "Kya student ID se travel kiya ja sakta hai?",
         "Haan, recognized school ya college dwara jari kiya gaya original photo student identity card travel ID ke roop me maanya hai (RUL-ID-01).",
         "Identity", "hi-en", 0, None),

        ("FAQ-020", "Train 3 ghante se zyada late ho to kya refund milega?",
         "Haan, RUL-DIS-01 Section 2 ke tahat agar train 3 ghante se adhik late hai aur aap yatra nahi karte hain, to departure se pehle TDR file karke poora refund le sakte hain.",
         "Refunds", "hi-en", 0, None)
    ]
    cursor.executemany("INSERT INTO faqs VALUES (?, ?, ?, ?, ?, ?, ?)", faqs)

    settings = [
        ("cancel_charge_1AC_over_48h", 240.0, "CIR-2026-01"),
        ("cancel_charge_2AC_over_48h", 200.0, "CIR-2026-01"),
        ("cancel_charge_3AC_over_48h", 180.0, "CIR-2026-01"),
        ("cancel_charge_SL_over_48h", 120.0, "RUL-CAN-01"),
        ("cancel_charge_2S_over_48h", 60.0, "RUL-CAN-01"),
        ("cancel_charge_pct_48h_to_12h", 25.0, "RUL-CAN-01"),
        ("cancel_charge_pct_12h_to_4h", 50.0, "RUL-CAN-01"),
        ("tatkal_charge_min_SL", 150.0, "CIR-2026-02"),
        ("tatkal_charge_min_3AC", 300.0, "CIR-2026-02"),
        ("boarding_change_cutoff_hours", 4.0, "RUL-BRD-01"),
        ("train_late_refund_cutoff_hours", 3.0, "RUL-DIS-01"),
        ("action_ttl_minutes", 10.0, "RUL-SYS-01")
    ]
    cursor.executemany("INSERT INTO settings VALUES (?, ?, ?)", settings)

def populate_stations_and_trains(cursor):
    stations = [
        ("PUNE", "Pune Junction", "Poona, Pune Jn", "Pune"),
        ("CSMT", "Chhatrapati Shivaji Maharaj Terminus", "Mumbai CSMT, CST, Bombay VT, Mumbai VT", "Mumbai"),
        ("BCT", "Mumbai Central", "Bombay Central, Mumbai BCT, BCT Main", "Mumbai"),
        ("KYN", "Kalyan Junction", "Kalyan Jn, Kalyan", "Kalyan"),
        ("BSL", "Bhusaval Junction", "Bhusawal, BSL Jn", "Bhusaval"),
        ("NGP", "Nagpur Junction", "Nagpur Jn, Orange City Station", "Nagpur"),
        ("SUR", "Solapur Junction", "Sholapur, Solapur Jn", "Solapur"),
        ("BPL", "Bhopal Junction", "Bhopal Jn, Bhopal Central", "Bhopal"),
        ("NDLS", "New Delhi", "Delhi, New Delhi Railway Station, DLI", "Delhi"),
        ("DDU", "Pt. Deen Dayal Upadhyaya Junction", "Mughalsarai, Mughalsarai Jn, DDU Jn", "Varanasi"),
        ("GKP", "Gorakhpur Junction", "Gorakhpur Jn, GKP", "Gorakhpur"),
        ("ADI", "Ahmedabad Junction", "Ahmedabad Jn, Kalupur Station", "Ahmedabad"),
        ("HWH", "Howrah Junction", "Howrah Jn, Kolkata HWH", "Kolkata"),
        ("MAO", "Madgaon Junction", "Margao, Madgaon Jn, Goa Station", "Goa"),
        ("JAT", "Jammu Tawi", "Jammu, Jammu Tawi Jn", "Jammu")
    ]
    cursor.executemany("INSERT INTO stations VALUES (?, ?, ?, ?)", stations)

    # 25 Trains
    trains = [
        ("12123", "Deccan Queen Express", "MON,TUE,WED,THU,FRI,SAT,SUN", "2AC,3AC,CC,2S"),
        ("12124", "Midnight Deccan Special", "MON,TUE,WED,THU,FRI,SAT,SUN", "2AC,3AC,SL"),
        ("12125", "Pragati Superfast Express", "MON,TUE,WED,THU,FRI,SAT,SUN", "3AC,CC,2S"),
        ("12127", "Mumbai Intercity Express", "MON,TUE,WED,THU,FRI,SAT,SUN", "CC,2S"),
        ("12137", "Punjab Mail Express", "MON,TUE,WED,THU,FRI,SAT,SUN", "1AC,2AC,3AC,SL"),
        ("12139", "Sewagram Superfast Express", "MON,TUE,WED,THU,FRI,SAT,SUN", "2AC,3AC,SL"),
        ("12157", "Hutatma Superfast Express", "MON,TUE,WED,THU,FRI,SAT,SUN", "3AC,CC,2S"),
        ("12163", "Ujjwal Solapur Superfast", "MON,TUE,WED,THU,FRI,SAT,SUN", "2AC,3AC,SL"),
        ("12221", "Pune Howrah Duronto", "MON,SAT", "1AC,2AC,3AC"),
        ("12289", "Mumbai Nagpur Duronto", "MON,TUE,WED,THU,FRI,SAT,SUN", "1AC,2AC,3AC,SL"),
        ("12290", "Nagpur Mumbai Duronto", "MON,TUE,WED,THU,FRI,SAT,SUN", "1AC,2AC,3AC,SL"),
        ("12431", "Rajdhani Express", "TUE,THU,FRI", "1AC,2AC,3AC"),
        ("12432", "Capital Rajdhani Special", "SUN,WED,SAT", "1AC,2AC,3AC"),
        ("12617", "Mangala Lakshadweep Express", "MON,TUE,WED,THU,FRI,SAT,SUN", "2AC,3AC,SL"),
        ("12951", "Mumbai Tejas Rajdhani", "MON,TUE,WED,THU,FRI,SAT,SUN", "1AC,2AC,3AC"),
        ("12952", "New Delhi Mumbai Tejas", "MON,TUE,WED,THU,FRI,SAT,SUN", "1AC,2AC,3AC"),
        ("12953", "August Kranti Tejas Rajdhani", "MON,TUE,WED,THU,FRI,SAT,SUN", "1AC,2AC,3AC"),
        ("15017", "Kashi Express", "MON,TUE,WED,THU,FRI,SAT,SUN", "2AC,3AC,SL"),
        ("15018", "Gorakhpur LTT Express", "MON,TUE,WED,THU,FRI,SAT,SUN", "2AC,3AC,SL"),
        ("16345", "Netravati Superfast Express", "MON,TUE,WED,THU,FRI,SAT,SUN", "2AC,3AC,SL"),
        ("19015", "Saurashtra Express", "MON,TUE,WED,THU,FRI,SAT,SUN", "3AC,SL,2S"),
        ("22105", "Indrayani Superfast Express", "MON,TUE,WED,THU,FRI,SAT,SUN", "CC,2S"),
        ("22106", "Pune Mumbai Superfast", "MON,TUE,WED,THU,FRI,SAT,SUN", "CC,2S"),
        ("02125", "Pune Nagpur Winter Special", "MON,TUE,WED,THU,FRI,SAT,SUN", "2AC,3AC,SL"),
        ("02126", "Nagpur Pune Winter Special", "MON,TUE,WED,THU,FRI,SAT,SUN", "2AC,3AC,SL")
    ]
    cursor.executemany("INSERT INTO trains VALUES (?, ?, ?, ?)", trains)

    # Detailed stops for ALL 25 trains
    train_stops = [
        # 12123: PUNE -> KYN -> CSMT
        ("12123", "PUNE", 1, "ORIGIN", "07:15", 0),
        ("12123", "KYN", 2, "09:20", "09:22", 0),
        ("12123", "CSMT", 3, "10:25", "DEST", 0),

        # 12124: PUNE -> KYN -> CSMT (Midnight departure: 00:25)
        ("12124", "PUNE", 1, "ORIGIN", "00:25", 0),
        ("12124", "KYN", 2, "02:40", "02:42", 0),
        ("12124", "CSMT", 3, "03:50", "DEST", 0),

        # 12125: PUNE -> KYN -> CSMT
        ("12125", "PUNE", 1, "ORIGIN", "16:30", 0),
        ("12125", "KYN", 2, "18:45", "18:47", 0),
        ("12125", "CSMT", 3, "19:50", "DEST", 0),

        # 12127: CSMT -> KYN -> PUNE
        ("12127", "CSMT", 1, "ORIGIN", "06:40", 0),
        ("12127", "KYN", 2, "07:42", "07:45", 0),
        ("12127", "PUNE", 3, "09:55", "DEST", 0),

        # 12137: CSMT -> KYN -> BSL -> BPL -> NDLS
        ("12137", "CSMT", 1, "ORIGIN", "19:35", 0),
        ("12137", "KYN", 2, "20:35", "20:38", 0),
        ("12137", "BSL", 3, "02:55", "03:00", 1),
        ("12137", "BPL", 4, "09:40", "09:45", 1),
        ("12137", "NDLS", 5, "21:30", "DEST", 1),

        # 12139: CSMT -> KYN -> BSL -> NGP
        ("12139", "CSMT", 1, "ORIGIN", "14:55", 0),
        ("12139", "KYN", 2, "15:52", "15:55", 0),
        ("12139", "BSL", 3, "21:30", "21:35", 0),
        ("12139", "NGP", 4, "05:45", "DEST", 1),

        # 12157: PUNE -> SUR
        ("12157", "PUNE", 1, "ORIGIN", "18:00", 0),
        ("12157", "SUR", 2, "22:15", "DEST", 0),

        # 12163: CSMT -> KYN -> PUNE -> SUR
        ("12163", "CSMT", 1, "ORIGIN", "18:45", 0),
        ("12163", "KYN", 2, "19:42", "19:45", 0),
        ("12163", "PUNE", 3, "22:35", "22:40", 0),
        ("12163", "SUR", 4, "03:10", "DEST", 1),

        # 12221: PUNE -> BSL -> NGP -> HWH
        ("12221", "PUNE", 1, "ORIGIN", "15:15", 0),
        ("12221", "BSL", 2, "21:10", "21:15", 0),
        ("12221", "NGP", 3, "02:00", "02:05", 1),
        ("12221", "HWH", 4, "20:15", "DEST", 1),

        # 12289: CSMT -> BSL -> NGP
        ("12289", "CSMT", 1, "ORIGIN", "20:15", 0),
        ("12289", "BSL", 2, "01:50", "01:55", 1),
        ("12289", "NGP", 3, "07:20", "DEST", 1),

        # 12290: NGP -> BSL -> CSMT
        ("12290", "NGP", 1, "ORIGIN", "20:40", 0),
        ("12290", "BSL", 2, "02:10", "02:15", 1),
        ("12290", "CSMT", 3, "08:05", "DEST", 1),

        # 12431: MAO -> BCT -> ADI -> NDLS
        ("12431", "MAO", 1, "ORIGIN", "11:20", 0),
        ("12431", "BCT", 2, "21:05", "21:10", 0),
        ("12431", "ADI", 3, "02:30", "02:35", 1),
        ("12431", "NDLS", 4, "12:40", "DEST", 1),

        # 12432: NDLS -> ADI -> BCT -> MAO
        ("12432", "NDLS", 1, "ORIGIN", "06:15", 0),
        ("12432", "ADI", 2, "16:20", "16:25", 0),
        ("12432", "BCT", 3, "22:15", "22:20", 0),
        ("12432", "MAO", 4, "08:30", "DEST", 1),

        # 12617: MAO -> KYN -> BSL -> BPL -> NDLS
        ("12617", "MAO", 1, "ORIGIN", "08:30", 0),
        ("12617", "KYN", 2, "19:12", "19:15", 0),
        ("12617", "BSL", 3, "01:40", "01:45", 1),
        ("12617", "BPL", 4, "08:20", "08:25", 1),
        ("12617", "NDLS", 5, "20:45", "DEST", 1),

        # 12951: BCT -> ADI -> NDLS
        ("12951", "BCT", 1, "ORIGIN", "17:00", 0),
        ("12951", "ADI", 2, "21:55", "22:00", 0),
        ("12951", "NDLS", 3, "08:32", "DEST", 1),

        # 12952: NDLS -> ADI -> BCT
        ("12952", "NDLS", 1, "ORIGIN", "16:55", 0),
        ("12952", "ADI", 2, "03:15", "03:20", 1),
        ("12952", "BCT", 3, "08:35", "DEST", 1),

        # 12953: BCT -> ADI -> NDLS
        ("12953", "BCT", 1, "ORIGIN", "17:40", 0),
        ("12953", "ADI", 2, "22:30", "22:35", 0),
        ("12953", "NDLS", 3, "09:43", "DEST", 1),

        # 15017: CSMT -> KYN -> BSL -> BPL -> DDU -> GKP
        ("15017", "CSMT", 1, "ORIGIN", "06:35", 0),
        ("15017", "KYN", 2, "07:37", "07:40", 0),
        ("15017", "BSL", 3, "14:15", "14:20", 0),
        ("15017", "BPL", 4, "21:20", "21:25", 0),
        ("15017", "DDU", 5, "10:10", "10:20", 1),
        ("15017", "GKP", 6, "18:50", "DEST", 1),

        # 15018: GKP -> DDU -> BPL -> BSL -> KYN -> CSMT
        ("15018", "GKP", 1, "ORIGIN", "05:45", 0),
        ("15018", "DDU", 2, "14:05", "14:15", 0),
        ("15018", "BPL", 3, "02:30", "02:35", 1),
        ("15018", "BSL", 4, "09:35", "09:40", 1),
        ("15018", "KYN", 5, "16:17", "16:20", 1),
        ("15018", "CSMT", 6, "17:30", "DEST", 1),

        # 16345: MAO -> PUNE -> KYN -> CSMT
        ("16345", "MAO", 1, "ORIGIN", "06:15", 0),
        ("16345", "PUNE", 2, "14:45", "14:50", 0),
        ("16345", "KYN", 3, "17:25", "17:28", 0),
        ("16345", "CSMT", 4, "18:35", "DEST", 0),

        # 19015: BCT -> ADI
        ("19015", "BCT", 1, "ORIGIN", "09:20", 0),
        ("19015", "ADI", 2, "18:10", "DEST", 0),

        # 22105: CSMT -> KYN -> PUNE
        ("22105", "CSMT", 1, "ORIGIN", "05:40", 0),
        ("22105", "KYN", 2, "06:33", "06:35", 0),
        ("22105", "PUNE", 3, "09:05", "DEST", 0),

        # 22106: PUNE -> KYN -> CSMT
        ("22106", "PUNE", 1, "ORIGIN", "18:35", 0),
        ("22106", "KYN", 2, "21:03", "21:05", 0),
        ("22106", "CSMT", 3, "22:15", "DEST", 0),

        # 02125: PUNE -> KYN -> BSL -> NGP
        ("02125", "PUNE", 1, "ORIGIN", "19:55", 0),
        ("02125", "KYN", 2, "22:10", "22:12", 0),
        ("02125", "BSL", 3, "04:15", "04:20", 1),
        ("02125", "NGP", 4, "11:45", "DEST", 1),

        # 02126: NGP -> BSL -> KYN -> PUNE
        ("02126", "NGP", 1, "ORIGIN", "19:40", 0),
        ("02126", "BSL", 2, "02:35", "02:40", 1),
        ("02126", "KYN", 3, "08:50", "08:52", 1),
        ("02126", "PUNE", 4, "11:25", "DEST", 1)
    ]
    cursor.executemany("INSERT INTO train_stops VALUES (?, ?, ?, ?, ?, ?)", train_stops)

def populate_fares_and_seats(cursor):
    # Fares for ALL 25 trains across their offered classes
    fares = [
        # 12123
        ("12123", "2AC", "PUNE", "CSMT", 840.0),
        ("12123", "3AC", "PUNE", "CSMT", 620.0),
        ("12123", "CC", "PUNE", "CSMT", 480.0),
        ("12123", "2S", "PUNE", "CSMT", 130.0),
        ("12123", "2AC", "PUNE", "KYN", 720.0),
        ("12123", "3AC", "PUNE", "KYN", 540.0),

        # 12124
        ("12124", "2AC", "PUNE", "CSMT", 840.0),
        ("12124", "3AC", "PUNE", "CSMT", 620.0),
        ("12124", "SL", "PUNE", "CSMT", 210.0),

        # 12125
        ("12125", "3AC", "PUNE", "CSMT", 620.0),
        ("12125", "CC", "PUNE", "CSMT", 480.0),
        ("12125", "2S", "PUNE", "CSMT", 130.0),

        # 12127
        ("12127", "CC", "CSMT", "PUNE", 480.0),
        ("12127", "2S", "CSMT", "PUNE", 130.0),

        # 12137
        ("12137", "1AC", "CSMT", "NDLS", 4450.0),
        ("12137", "2AC", "CSMT", "NDLS", 2980.0),
        ("12137", "3AC", "CSMT", "NDLS", 2100.0),
        ("12137", "SL", "CSMT", "NDLS", 780.0),

        # 12139
        ("12139", "2AC", "CSMT", "NGP", 1980.0),
        ("12139", "3AC", "CSMT", "NGP", 1410.0),
        ("12139", "SL", "CSMT", "NGP", 540.0),

        # 12157
        ("12157", "3AC", "PUNE", "SUR", 680.0),
        ("12157", "CC", "PUNE", "SUR", 520.0),
        ("12157", "2S", "PUNE", "SUR", 160.0),

        # 12163
        ("12163", "2AC", "CSMT", "SUR", 1450.0),
        ("12163", "3AC", "CSMT", "SUR", 1020.0),
        ("12163", "SL", "CSMT", "SUR", 390.0),

        # 12221
        ("12221", "1AC", "PUNE", "HWH", 4850.0),
        ("12221", "2AC", "PUNE", "HWH", 3350.0),
        ("12221", "3AC", "PUNE", "HWH", 2390.0),

        # 12289
        ("12289", "1AC", "CSMT", "NGP", 3250.0),
        ("12289", "2AC", "CSMT", "NGP", 2120.0),
        ("12289", "3AC", "CSMT", "NGP", 1530.0),
        ("12289", "SL", "CSMT", "NGP", 590.0),

        # 12290
        ("12290", "1AC", "NGP", "CSMT", 3250.0),
        ("12290", "2AC", "NGP", "CSMT", 2120.0),
        ("12290", "3AC", "NGP", "CSMT", 1530.0),
        ("12290", "SL", "NGP", "CSMT", 590.0),

        # 12431
        ("12431", "1AC", "MAO", "NDLS", 5200.0),
        ("12431", "2AC", "MAO", "NDLS", 3650.0),
        ("12431", "3AC", "MAO", "NDLS", 2620.0),

        # 12432
        ("12432", "1AC", "NDLS", "MAO", 5200.0),
        ("12432", "2AC", "NDLS", "MAO", 3650.0),
        ("12432", "3AC", "NDLS", "MAO", 2620.0),

        # 12617
        ("12617", "2AC", "MAO", "NDLS", 3450.0),
        ("12617", "3AC", "MAO", "NDLS", 2420.0),
        ("12617", "SL", "MAO", "NDLS", 910.0),

        # 12951
        ("12951", "1AC", "BCT", "NDLS", 4650.0),
        ("12951", "2AC", "BCT", "NDLS", 3100.0),
        ("12951", "3AC", "BCT", "NDLS", 2250.0),

        # 12952
        ("12952", "1AC", "NDLS", "BCT", 4650.0),
        ("12952", "2AC", "NDLS", "BCT", 3100.0),
        ("12952", "3AC", "NDLS", "BCT", 2250.0),

        # 12953
        ("12953", "1AC", "BCT", "NDLS", 4650.0),
        ("12953", "2AC", "BCT", "NDLS", 3100.0),
        ("12953", "3AC", "BCT", "NDLS", 2250.0),

        # 15017
        ("15017", "2AC", "CSMT", "GKP", 2650.0),
        ("15017", "3AC", "CSMT", "GKP", 1840.0),
        ("15017", "SL", "CSMT", "GKP", 720.0),

        # 15018
        ("15018", "2AC", "GKP", "CSMT", 2650.0),
        ("15018", "3AC", "GKP", "CSMT", 1840.0),
        ("15018", "SL", "GKP", "CSMT", 720.0),

        # 16345
        ("16345", "2AC", "MAO", "CSMT", 1850.0),
        ("16345", "3AC", "MAO", "CSMT", 1320.0),
        ("16345", "SL", "MAO", "CSMT", 490.0),

        # 19015
        ("19015", "3AC", "BCT", "ADI", 1150.0),
        ("19015", "SL", "BCT", "ADI", 420.0),
        ("19015", "2S", "BCT", "ADI", 190.0),

        # 22105
        ("22105", "CC", "CSMT", "PUNE", 480.0),
        ("22105", "2S", "CSMT", "PUNE", 130.0),

        # 22106
        ("22106", "CC", "PUNE", "CSMT", 480.0),
        ("22106", "2S", "PUNE", "CSMT", 130.0),

        # 02125
        ("02125", "2AC", "PUNE", "NGP", 2040.0),
        ("02125", "3AC", "PUNE", "NGP", 1450.0),
        ("02125", "SL", "PUNE", "NGP", 560.0),

        # 02126
        ("02126", "2AC", "NGP", "PUNE", 2040.0),
        ("02126", "3AC", "NGP", "PUNE", 1450.0),
        ("02126", "SL", "NGP", "PUNE", 560.0)
    ]
    cursor.executemany("INSERT INTO fares VALUES (?, ?, ?, ?, ?)", fares)

    # 14-day rolling seat availability for ALL 25 trains and their classes
    base_date = datetime.date(2026, 11, 21)
    train_class_map = {
        "12123": ["2AC", "3AC", "CC", "2S"],
        "12124": ["2AC", "3AC", "SL"],
        "12125": ["3AC", "CC", "2S"],
        "12127": ["CC", "2S"],
        "12137": ["1AC", "2AC", "3AC", "SL"],
        "12139": ["2AC", "3AC", "SL"],
        "12157": ["3AC", "CC", "2S"],
        "12163": ["2AC", "3AC", "SL"],
        "12221": ["1AC", "2AC", "3AC"],
        "12289": ["1AC", "2AC", "3AC", "SL"],
        "12290": ["1AC", "2AC", "3AC", "SL"],
        "12431": ["1AC", "2AC", "3AC"],
        "12432": ["1AC", "2AC", "3AC"],
        "12617": ["2AC", "3AC", "SL"],
        "12951": ["1AC", "2AC", "3AC"],
        "12952": ["1AC", "2AC", "3AC"],
        "12953": ["1AC", "2AC", "3AC"],
        "15017": ["2AC", "3AC", "SL"],
        "15018": ["2AC", "3AC", "SL"],
        "16345": ["2AC", "3AC", "SL"],
        "19015": ["3AC", "SL", "2S"],
        "22105": ["CC", "2S"],
        "22106": ["CC", "2S"],
        "02125": ["2AC", "3AC", "SL"],
        "02126": ["2AC", "3AC", "SL"]
    }

    seat_records = []
    for day in range(15): # 14 days + 1 extra
        j_date = (base_date + datetime.timedelta(days=day)).isoformat()
        for t_no, classes in train_class_map.items():
            for cls in classes:
                # Deterministic availability with diverse conditions: Available, RAC, WL, Full
                if day == 0 and t_no in ["12123", "12124"]:
                    avail, rac, wl = 0, 4, 10
                elif day == 1 and cls == "2AC":
                    avail, rac, wl = 0, 6, 0
                elif day == 2 and cls == "3AC":
                    avail, rac, wl = 0, 0, 15
                elif day > 4:
                    avail, rac, wl = 25 if "AC" in cls else 65, 0, 0
                else:
                    avail, rac, wl = 8, 2, 0
                seat_records.append((t_no, j_date, cls, avail, rac, wl))

    cursor.executemany("INSERT INTO seats VALUES (?, ?, ?, ?, ?, ?)", seat_records)

def populate_passengers_bookings_and_travellers(cursor):
    passengers = [
        ("PASS-001", "Aarav Sharma", "7821", "en"),
        ("PASS-002", "Priya Kulkarni", "9102", "mr"),
        ("PASS-003", "Rohan Mehta", "4512", "gu"),
        ("PASS-004", "Neha Verma", "3391", "hi"),
        ("PASS-005", "Vikram Malhotra", "8823", "en"),
        ("PASS-006", "Ananya Deshmukh", "1290", "mr"),
        ("PASS-007", "Suresh Patel", "6734", "gu"),
        ("PASS-008", "Sunita Rao", "9011", "en"),
        ("PASS-009", "Amitabh Joshi", "4410", "hi"),
        ("PASS-010", "Kavita Nair", "5512", "en"),
        ("PASS-011", "Manoj Tiwari", "7789", "hi"),
        ("PASS-012", "Pooja Hegde", "6621", "en"),
        ("PASS-013", "Rajeshwari Iyer", "4401", "en"),
        ("PASS-014", "Deepak Chawla", "8810", "hi"),
        ("PASS-015", "Tanvi Shinde", "1198", "mr"),
        ("PASS-016", "Nikhil Bansal", "9921", "en"),
        ("PASS-017", "Swati Gokhale", "3345", "mr"),
        ("PASS-018", "Alok Pandey", "5567", "hi"),
        ("PASS-019", "Meera Sen", "7712", "en"),
        ("PASS-020", "Girish Karnad", "8834", "en"),
        ("PASS-021", "Bhavna Shah", "2219", "gu"),
        ("PASS-022", "Kunal Kamra", "4490", "hi"),
        ("PASS-023", "Shalini Patil", "6612", "mr"),
        ("PASS-024", "Vivek Agnihotri", "9901", "hi"),
        ("PASS-025", "Rajesh Deshmukh", "3311", "mr") # Awkward case: zero bookings!
    ]
    cursor.executemany("INSERT INTO passengers VALUES (?, ?, ?, ?)", passengers)

    # 51 Bookings covering all statuses
    bookings = [
        # Awkward Cut-off cases
        ("UR-30418", "PASS-001", "02125", "2026-12-05", "PUNE", "NGP", "2AC", 2040.0, "CONFIRMED", "2026-11-10T14:30:00"),
        ("UR-30419", "PASS-001", "12123", "2026-11-23", "PUNE", "CSMT", "2AC", 840.0, "CONFIRMED", "2026-11-12T10:15:00"),

        # Awkward Mixed Status Case
        ("UR-50012", "PASS-002", "12123", "2026-11-25", "PUNE", "CSMT", "3AC", 1240.0, "CONFIRMED", "2026-11-14T11:20:00"),

        # Midnight departure booking
        ("UR-12124-B1", "PASS-003", "12124", "2026-11-22", "PUNE", "CSMT", "2AC", 840.0, "CONFIRMED", "2026-11-15T09:00:00"),

        # Confirmed Bookings
        ("UR-10001", "PASS-001", "12123", "2026-11-22", "PUNE", "CSMT", "CC", 480.0, "CONFIRMED", "2026-11-05T08:00:00"),
        ("UR-10002", "PASS-004", "12124", "2026-11-23", "PUNE", "CSMT", "3AC", 620.0, "CONFIRMED", "2026-11-06T09:00:00"),
        ("UR-10003", "PASS-005", "12289", "2026-11-24", "CSMT", "NGP", "2AC", 2120.0, "CONFIRMED", "2026-11-07T10:00:00"),
        ("UR-10004", "PASS-006", "02125", "2026-11-25", "PUNE", "NGP", "2AC", 2040.0, "CONFIRMED", "2026-11-08T11:00:00"),
        ("UR-10005", "PASS-007", "12157", "2026-11-29", "PUNE", "SUR", "CC", 520.0, "CONFIRMED", "2026-11-09T12:00:00"),
        ("UR-10006", "PASS-008", "12951", "2026-11-26", "BCT", "NDLS", "3AC", 2250.0, "CONFIRMED", "2026-11-10T13:00:00"),
        ("UR-10007", "PASS-009", "15017", "2026-12-01", "CSMT", "GKP", "SL", 720.0, "CONFIRMED", "2026-11-11T14:00:00"),
        ("UR-10008", "PASS-010", "12139", "2026-12-02", "CSMT", "NGP", "2AC", 1980.0, "CONFIRMED", "2026-11-12T15:00:00"),
        ("UR-10009", "PASS-011", "12137", "2026-11-28", "CSMT", "NDLS", "1AC", 4450.0, "CONFIRMED", "2026-11-13T16:00:00"),
        ("UR-10010", "PASS-012", "12123", "2026-11-24", "PUNE", "CSMT", "3AC", 620.0, "CONFIRMED", "2026-11-14T17:00:00"),
        ("UR-10011", "PASS-013", "12127", "2026-11-25", "CSMT", "PUNE", "CC", 480.0, "CONFIRMED", "2026-11-15T18:00:00"),
        ("UR-10012", "PASS-014", "12157", "2026-11-24", "PUNE", "SUR", "3AC", 680.0, "CONFIRMED", "2026-11-16T19:00:00"),
        ("UR-10013", "PASS-003", "12123", "2026-11-26", "PUNE", "CSMT", "3AC", 620.0, "CONFIRMED", "2026-11-10T09:30:00"),
        ("UR-10014", "PASS-015", "12163", "2026-11-27", "CSMT", "SUR", "2AC", 1450.0, "CONFIRMED", "2026-11-11T11:45:00"),

        # RAC Bookings
        ("UR-20001", "PASS-002", "12124", "2026-11-21", "PUNE", "CSMT", "SL", 210.0, "RAC", "2026-11-13T10:00:00"),
        ("UR-20002", "PASS-003", "12289", "2026-11-22", "CSMT", "NGP", "2AC", 2120.0, "RAC", "2026-11-14T11:00:00"),
        ("UR-20003", "PASS-005", "02125", "2026-11-22", "PUNE", "NGP", "2AC", 2040.0, "RAC", "2026-11-15T12:00:00"),
        ("UR-20004", "PASS-006", "12123", "2026-11-22", "PUNE", "CSMT", "2AC", 840.0, "RAC", "2026-11-16T13:00:00"),
        ("UR-20005", "PASS-008", "12139", "2026-11-23", "CSMT", "NGP", "SL", 540.0, "RAC", "2026-11-17T14:00:00"),
        ("UR-20006", "PASS-015", "12124", "2026-11-23", "PUNE", "CSMT", "3AC", 620.0, "RAC", "2026-11-18T15:00:00"),
        ("UR-20007", "PASS-016", "12289", "2026-11-24", "CSMT", "NGP", "3AC", 1530.0, "RAC", "2026-11-19T16:00:00"),
        ("UR-20008", "PASS-017", "02125", "2026-11-25", "PUNE", "NGP", "SL", 560.0, "RAC", "2026-11-20T17:00:00"),

        # Waitlisted Bookings
        ("UR-30001", "PASS-004", "12124", "2026-11-21", "PUNE", "CSMT", "3AC", 620.0, "WL", "2026-11-16T18:00:00"),
        ("UR-30002", "PASS-007", "12289", "2026-11-21", "CSMT", "NGP", "2AC", 2120.0, "WL", "2026-11-17T19:00:00"),
        ("UR-30003", "PASS-009", "02125", "2026-11-22", "PUNE", "NGP", "3AC", 1450.0, "WL", "2026-11-18T20:00:00"),
        ("UR-30004", "PASS-011", "12124", "2026-11-22", "PUNE", "CSMT", "SL", 210.0, "WL", "2026-11-19T21:00:00"),
        ("UR-30005", "PASS-018", "12123", "2026-11-22", "PUNE", "CSMT", "3AC", 620.0, "WL", "2026-11-20T22:00:00"),
        ("UR-30006", "PASS-019", "12139", "2026-11-22", "CSMT", "NGP", "2AC", 1980.0, "WL", "2026-11-20T23:00:00"),
        ("UR-30007", "PASS-020", "15017", "2026-11-23", "CSMT", "GKP", "2AC", 2650.0, "WL", "2026-11-21T06:00:00"),
        ("UR-30008", "PASS-021", "12124", "2026-11-23", "PUNE", "CSMT", "SL", 210.0, "WL", "2026-11-21T07:00:00"),

        # Cancelled Bookings (by passenger)
        ("UR-40001", "PASS-001", "12123", "2026-11-15", "PUNE", "CSMT", "CC", 480.0, "CANCELLED", "2026-11-01T08:00:00"),
        ("UR-40002", "PASS-002", "12289", "2026-11-16", "CSMT", "NGP", "2AC", 2120.0, "CANCELLED", "2026-11-02T09:00:00"),
        ("UR-40003", "PASS-003", "12951", "2026-11-17", "BCT", "NDLS", "3AC", 2250.0, "CANCELLED", "2026-11-03T10:00:00"),
        ("UR-40004", "PASS-005", "12157", "2026-11-18", "PUNE", "SUR", "2S", 160.0, "CANCELLED", "2026-11-04T11:00:00"),
        ("UR-40005", "PASS-006", "02125", "2026-11-19", "PUNE", "NGP", "SL", 560.0, "CANCELLED", "2026-11-05T12:00:00"),
        ("UR-40006", "PASS-010", "15017", "2026-11-20", "CSMT", "GKP", "3AC", 1840.0, "CANCELLED", "2026-11-06T13:00:00"),
        ("UR-40007", "PASS-012", "12139", "2026-11-21", "CSMT", "NGP", "SL", 540.0, "CANCELLED", "2026-11-07T14:00:00"),
        ("UR-40008", "PASS-014", "12124", "2026-11-20", "PUNE", "CSMT", "2AC", 840.0, "CANCELLED", "2026-11-08T15:00:00"),

        # Operator Cancelled Bookings (Train cancelled by railway operator)
        ("UR-50001", "PASS-001", "12125", "2026-11-18", "PUNE", "CSMT", "CC", 480.0, "OPERATOR_CANCELLED", "2026-11-05T10:00:00"),
        ("UR-50002", "PASS-004", "12125", "2026-11-18", "PUNE", "CSMT", "3AC", 620.0, "OPERATOR_CANCELLED", "2026-11-05T11:00:00"),
        ("UR-50003", "PASS-007", "02125", "2026-11-22", "PUNE", "NGP", "2AC", 2040.0, "OPERATOR_CANCELLED", "2026-11-01T12:00:00"),
        ("UR-50004", "PASS-011", "02125", "2026-11-22", "PUNE", "NGP", "3AC", 1450.0, "OPERATOR_CANCELLED", "2026-11-02T13:00:00"),
        ("UR-50005", "PASS-013", "12125", "2026-11-22", "PUNE", "CSMT", "2S", 130.0, "OPERATOR_CANCELLED", "2026-11-06T14:00:00"),
        ("UR-50006", "PASS-016", "15017", "2026-11-23", "CSMT", "GKP", "SL", 720.0, "OPERATOR_CANCELLED", "2026-10-28T15:00:00"),
        ("UR-50007", "PASS-022", "12139", "2026-11-22", "CSMT", "NGP", "2AC", 1980.0, "OPERATOR_CANCELLED", "2026-10-25T16:00:00"),
        ("UR-50008", "PASS-023", "12951", "2026-11-23", "BCT", "NDLS", "1AC", 4650.0, "OPERATOR_CANCELLED", "2026-10-26T17:00:00"),
        ("UR-50009", "PASS-024", "12157", "2026-11-24", "PUNE", "SUR", "CC", 520.0, "OPERATOR_CANCELLED", "2026-10-29T18:00:00")
    ]
    cursor.executemany("INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", bookings)

    # Booking Travellers - ALL 51 Bookings have full traveller records!
    # Mapping passenger_id to name
    p_names = {p[0]: p[1] for p in passengers}
    travellers = []
    
    # Specific Awkward cases
    travellers.append(("UR-30418", "Aarav Sharma", 32, "CNF", "A1", "17"))
    travellers.append(("UR-30419", "Aarav Sharma", 32, "CNF", "A2", "09"))
    travellers.append(("UR-50012", "Priya Kulkarni", 28, "CNF", "B1", "23"))
    travellers.append(("UR-50012", "Rahul Kulkarni", 31, "WL", None, None)) # Mixed status!
    travellers.append(("UR-12124-B1", "Rohan Mehta", 45, "CNF", "A1", "04"))

    assigned = {"UR-30418", "UR-30419", "UR-50012", "UR-12124-B1"}
    
    coach_map = {"1AC": "H1", "2AC": "A1", "3AC": "B1", "CC": "C1", "SL": "S1", "2S": "D1"}
    
    for b in bookings:
        b_id, p_id, t_no, j_dt, f_c, to_c, cls, amt, status, b_at = b
        if b_id in assigned:
            continue
        
        name = p_names.get(p_id, "Passenger Name")
        if status == "CONFIRMED":
            trav_status = "CNF"
            coach = coach_map.get(cls, "B1")
            berth = "15"
        elif status == "RAC":
            trav_status = "RAC"
            coach = coach_map.get(cls, "S1")
            berth = "Berth 07-Shared"
        elif status == "WL":
            trav_status = "WL"
            coach = None
            berth = None
        elif status == "CANCELLED":
            trav_status = "CAN"
            coach = None
            berth = None
        else: # OPERATOR_CANCELLED
            trav_status = "CAN_OP"
            coach = None
            berth = None

        travellers.append((b_id, name, 35, trav_status, coach, berth))

    cursor.executemany("INSERT INTO booking_travellers VALUES (?, ?, ?, ?, ?, ?)", travellers)

    # Actions table
    actions = [
        ("ACT-0091", "PASS-001", "UR-30418", "cancel_booking", "PENDING", 
         "2026-11-21T10:15:00+05:30", "2026-11-21T10:25:00+05:30", None),
        ("ACT-0082", "PASS-002", "UR-20001", "change_boarding", "COMPLETED", 
         "2026-11-20T14:00:00+05:30", "2026-11-20T14:10:00+05:30", "Boarding changed to KYN"),
        ("ACT-0073", "PASS-004", "UR-30001", "cancel_booking", "EXPIRED", 
         "2026-11-19T09:00:00+05:30", "2026-11-19T09:10:00+05:30", "Expired without confirmation"),
        ("ACT-0064", "PASS-006", "UR-10004", "cancel_booking", "CANCELLED", 
         "2026-11-18T18:20:00+05:30", "2026-11-18T18:30:00+05:30", "Dropped by passenger")
    ]
    cursor.executemany("INSERT INTO actions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", actions)

def populate_audit_logs(cursor):
    # 3 Sample Audit Records required by Section 8 (including full cancellation lifecycle)
    audit_records = [
        (
            "b17e40c2",
            "sess-9901",
            "PASS-001",
            "2026-11-21T10:15:00+05:30",
            "Cancel my booking UR-30418 for Pune to Nagpur.",
            "confirm_needed",
            "Cancelling booking UR-30418 (02125, Pune to Nagpur, 05 Dec, 2AC, 1 seat) now gives you a refund of Rs 1,840 (deduction Rs 200). Shall I go ahead?",
            json.dumps([{"doc_id": "RUL-CAN-01", "section": "1. Cut-off Tiers"}, {"doc_id": "CIR-2026-01", "section": "Revised charges"}]),
            json.dumps([{"tool": "refund_quote", "output": {"amount_paid": 2040, "charge": 200, "refund": 1840, "hours_before_departure": 338}}]),
            json.dumps({"action_id": "ACT-0091", "type": "cancel_booking", "booking_id": "UR-30418", "expires_at": "2026-11-21T10:25:00+05:30"}),
            None
        ),
        (
            "c28f51d3",
            "sess-9901",
            "PASS-001",
            "2026-11-21T10:16:30+05:30",
            "POST /actions/ACT-0091/confirm",
            "action_done",
            "Booking UR-30418 has been successfully cancelled. Refund of Rs 1,840 has been processed to your original payment method.",
            json.dumps([{"doc_id": "RUL-CAN-01", "section": "1. Cut-off Tiers"}]),
            json.dumps([{"tool": "execute_cancellation", "output": {"status": "SUCCESS", "booking_id": "UR-30418", "refund_amount": 1840}}]),
            None,
            None
        ),
        (
            "d39a62e4",
            "sess-9902",
            "PASS-004",
            "2026-11-21T10:20:00+05:30",
            "My train was cancelled 10 days ago and I still haven't got my money. I want to complain.",
            "handed_to_human",
            "I have transferred your grievance regarding delayed cancellation refund for booking UR-50002 to our Complaints and Escalations Desk. Ticket ID #ESC-8841 has been created.",
            json.dumps([{"doc_id": "RUL-CMP-01", "section": "1. Grievance Redressal"}, {"doc_id": "RUL-DIS-01", "section": "1. Train Cancelled by Operator"}]),
            json.dumps([{"tool": "escalate_to_human", "output": {"desk": "Complaints Desk", "ticket_id": "ESC-8841", "booking_id": "UR-50002"}}]),
            None,
            json.dumps({"desk": "Complaints Desk", "ticket_id": "ESC-8841", "passenger_id": "PASS-004", "booking_id": "UR-50002", "summary": "Delayed refund for operator-cancelled train"})
        )
    ]
    cursor.executemany("INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", audit_records)

def export_knowledge_pack(cursor):
    cursor.execute("SELECT * FROM rules")
    rules_data = [dict(row) for row in cursor.fetchall()]
    cursor.execute("SELECT * FROM circulars")
    circulars_data = [dict(row) for row in cursor.fetchall()]
    cursor.execute("SELECT * FROM faqs")
    faqs_data = [dict(row) for row in cursor.fetchall()]

    knowledge_pack = {
        "operator": "Ujjwal Rail",
        "generated_at": datetime.datetime.now().isoformat(),
        "rules_count": len(rules_data),
        "circulars_count": len(circulars_data),
        "faqs_count": len(faqs_data),
        "rules": rules_data,
        "circulars": circulars_data,
        "faqs": faqs_data
    }

    kp_path = os.path.join(CURRENT_DIR, "knowledge_pack.json")
    with open(kp_path, "w", encoding="utf-8") as f:
        json.dump(knowledge_pack, f, indent=2, ensure_ascii=False)

def main():
    os.makedirs(CURRENT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("1. Initializing Tables...")
    init_db(cursor)

    print("2. Populating Rules, Circulars, FAQs, and Settings...")
    populate_rules_and_circulars(cursor)

    print("3. Populating Stations and Trains (All 25 with full stops)...")
    populate_stations_and_trains(cursor)

    print("4. Populating Fares and 14-Day Seats (All 25 trains)...")
    populate_fares_and_seats(cursor)

    print("5. Populating Passengers, Bookings, and Travellers (All 51 bookings)...")
    populate_passengers_bookings_and_travellers(cursor)

    print("6. Populating Audit Logs (3 Sample Audit Records)...")
    populate_audit_logs(cursor)

    conn.commit()

    print("7. Exporting Knowledge Pack JSON...")
    export_knowledge_pack(cursor)

    conn.close()
    print("SUCCESS: Database generated cleanly at:", DB_PATH)

if __name__ == "__main__":
    main()
