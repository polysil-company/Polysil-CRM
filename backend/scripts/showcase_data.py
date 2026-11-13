"""The showcase dataset, as data: what `seed_showcase.py` creates through the API.

Everything here is invented for the demo. District names and codes are Gujarat's
own (public information; the codes are the client's abbreviations); talukas are
real; villages, people, dealers and leads are fictional and any resemblance is
accidental. Nothing in this file is client-confidential, so it lives beside the
seed rather than under data/.
"""
from __future__ import annotations

# ── territories ──────────────────────────────────────────────────────────────

STATE = ("Gujarat", "GJ")

# The 33 districts with the abbreviations the client's sheets use (the client's
# intake). Baroda appears in the client's list as an alias of Vadodara and is
# folded into it here.
DISTRICTS: list[tuple[str, str]] = [
    ("Ahmedabad", "AMD"), ("Amreli", "AMR"), ("Anand", "AND"), ("Aravalli", "ARV"),
    ("Banaskantha", "BK"), ("Bharuch", "BHR"), ("Bhavnagar", "BVN"), ("Botad", "BTD"),
    ("Chhota Udepur", "CTU"), ("Dahod", "DH"), ("Dang", "DN"), ("Devbhumi Dwarka", "DBD"),
    ("Gandhinagar", "GN"), ("Gir Somnath", "GS"), ("Jamnagar", "JMN"), ("Junagadh", "JND"),
    ("Kheda", "KH"), ("Kutch", "KCT"), ("Mahisagar", "MH"), ("Mehsana", "MSN"),
    ("Morbi", "MRB"), ("Narmada", "NMD"), ("Navsari", "NVS"), ("Panchmahal", "PM"),
    ("Patan", "PTN"), ("Porbandar", "PBR"), ("Rajkot", "RJT"), ("Sabarkantha", "SK"),
    ("Surat", "SRT"), ("Surendranagar", "SNR"), ("Tapi", "TP"), ("Vadodara", "BRD"),
    ("Valsad", "VLD"),
]

# district -> talukas -> villages. Three districts carry the demo's field work.
TALUKAS: dict[str, dict[str, list[str]]] = {
    "Rajkot": {
        "Gondal": ["Virpur", "Kolithad", "Shivrajpur", "Bhadar", "Vavdi"],
        "Jetpur": ["Khirasara", "Nagalpar", "Devki Gadhda", "Pithadiya"],
        "Jasdan": ["Atkot", "Vinchhiya Road", "Kamalapur", "Bhadla"],
        "Dhoraji": ["Supedi", "Patanvav", "Bhukhi"],
        "Upleta": ["Kolki", "Moti Panelii", "Bhayavadar"],
    },
    "Junagadh": {
        "Keshod": ["Balagam", "Ajab", "Mangrol Road"],
        "Manavadar": ["Bantva", "Sardargadh", "Vadal"],
        "Vanthali": ["Khorasa", "Sukhpur", "Dhandhusar"],
        "Visavadar": ["Bhalchhel", "Kalsari", "Sanosari"],
    },
    "Amreli": {
        "Babra": ["Chamardi", "Jaliya", "Kotda Pitha"],
        "Savarkundla": ["Vijpadi", "Thordi", "Dedan"],
        "Dhari": ["Khambha Road", "Gopalgram", "Dalkhania"],
        "Lathi": ["Damnagar", "Chavand", "Ansodar"],
    },
}

# ── the company ──────────────────────────────────────────────────────────────

# (name, role_level, parent, territory). HQ units carry no territory (RBAC 4).
OFFICES: list[tuple[str, int, str | None, str | None]] = [
    ("HQ Accounts", 5, "Polysil HQ", None),
    ("HQ Dispatch", 5, "Polysil HQ", None),
    ("HQ Quality", 5, "Polysil HQ", None),
    ("HQ Marketing", 5, "Polysil HQ", None),
    ("HQ Support", 5, "Polysil HQ", None),
    ("HQ Subsidy", 5, "Polysil HQ", None),
    ("Region West", 4, "Polysil HQ", "Gujarat"),
    ("Gujarat State", 3, "Region West", "Gujarat"),
    ("Rajkot District", 2, "Gujarat State", "Rajkot"),
    ("Junagadh District", 2, "Gujarat State", "Junagadh"),
    ("Amreli District", 2, "Gujarat State", "Amreli"),
    ("Gondal Field", 1, "Rajkot District", "Gondal"),
    ("Jetpur Field", 1, "Rajkot District", "Jetpur"),
    ("Keshod Field", 1, "Junagadh District", "Keshod"),
    ("Manavadar Field", 1, "Junagadh District", "Manavadar"),
    ("Babra Field", 1, "Amreli District", "Babra"),
    ("Savarkundla Field", 1, "Amreli District", "Savarkundla"),
]

# (email local part, full name, role code, office, territories the person covers).
# Territories only matter for the territory-scoped roles.
STAFF: list[tuple[str, str, str, str, list[str]]] = [
    ("md", "Hasmukh Vekariya", "md_ceo", "Polysil HQ", []),
    ("board", "Ilaben Radadiya", "board", "Polysil HQ", []),
    ("accounts", "Nilesh Dobariya", "account_manager", "HQ Accounts", []),
    ("dispatch", "Jignesh Sojitra", "dispatch_manager", "HQ Dispatch", []),
    ("quality", "Kirit Bhalodiya", "qc_manager", "HQ Quality", []),
    ("marketing", "Payal Gajera", "marketing", "HQ Marketing", []),
    ("support", "Dipak Savaliya", "support", "HQ Support", []),
    ("coordinator", "Hetal Kathiriya", "state_coordinator", "HQ Subsidy", ["Rajkot", "Junagadh"]),
    ("west", "Rajesh Jadeja", "regional_manager", "Region West", []),
    ("gujarat", "Meena Gohil", "state_manager", "Gujarat State", []),
    ("asha", "Asha Patel", "district_manager", "Rajkot District", []),   # the demo seed's
    ("junagadh", "Bharat Vaghela", "district_manager", "Junagadh District", []),
    ("amreli", "Kajal Solanki", "district_manager", "Amreli District", []),
    ("ravi", "Ravi Solanki", "field_officer", "Gondal Field", []),
    ("mehul", "Mehul Kathiriya", "field_officer", "Jetpur Field", []),
    ("sanjay", "Sanjay Ahir", "field_officer", "Keshod Field", []),
    ("pooja", "Pooja Dobariya", "field_officer", "Manavadar Field", []),
    ("vipul", "Vipul Sojitra", "field_officer", "Babra Field", []),
    ("rina", "Rina Vekariya", "field_officer", "Savarkundla Field", []),
]

# ── the channel ──────────────────────────────────────────────────────────────

# (code, name, type, parent code, district, user name, user mobile)
PARTNERS: list[tuple[str, str, str, str | None, str, str, str]] = [
    # Bhavesh Shah (919876543210) is the demo seed's dealer user and stays there;
    # the showcase distributor gets its own person.
    ("DIST-SAU", "Saurashtra Agro Distributors", "distributor", None, "Rajkot",
     "Mahesh Shah", "919876543220"),
    ("DIST-SOR", "Sorath Agri Distributors", "distributor", None, "Junagadh",
     "Mansukh Radadiya", "919876543211"),
    ("DLR-GONDAL", "Shree Ganesh Agro Agency, Gondal", "dealer", "DIST-SAU", "Rajkot",
     "Chirag Patel", "919876543212"),
    ("DLR-JETPUR", "Khodiyar Irrigation, Jetpur", "dealer", "DIST-SAU", "Rajkot",
     "Hitesh Gohil", "919876543213"),
    ("DLR-KESHOD", "Patel Agro Traders, Keshod", "dealer", "DIST-SOR", "Junagadh",
     "Nitin Patel", "919876543214"),
    ("DLR-AMRELI", "Ambika Krishi Kendra, Amreli", "dealer", "DIST-SOR", "Amreli",
     "Jayesh Bhalodiya", "919876543215"),
    ("DLR-RAJKOT", "Saurashtra Drip Solutions, Rajkot", "dealer", "DIST-SAU", "Rajkot",
     "Kiran Dave", "919876543216"),
    ("SUB-VIRPUR", "Virpur Agro Point", "sub_dealer", "DLR-GONDAL", "Rajkot",
     "Alpesh Sojitra", "919876543217"),
    ("SUB-BALAGAM", "Balagam Krishi Seva", "sub_dealer", "DLR-KESHOD", "Junagadh",
     "Ramesh Ahir", "919876543218"),
    ("SUB-BABRA", "Babra Farm Supplies", "sub_dealer", "DLR-AMRELI", "Amreli",
     "Gopal Vaghela", "919876543219"),
]

# ── leads ────────────────────────────────────────────────────────────────────

FARMER_FIRST = ["Kanubhai", "Rameshbhai", "Jayantibhai", "Bhupatbhai", "Dineshbhai",
                "Manjulaben", "Hansaben", "Vallabhbhai", "Prakashbhai", "Govindbhai",
                "Lalitaben", "Arvindbhai", "Nareshbhai", "Savitaben", "Bhikhabhai",
                "Chhaganbhai", "Kantibhai", "Gitaben", "Maganbhai", "Vinodbhai"]
FARMER_LAST = ["Desai", "Kathiriya", "Sojitra", "Dobariya", "Vaghela", "Gohil", "Jadeja",
               "Solanki", "Ahir", "Vekariya", "Radadiya", "Savaliya", "Bhalodiya", "Gajera",
               "Ramani", "Kalariya", "Hirpara", "Sakhiya", "Dudhat", "Chovatiya"]

CROPS = ["cotton", "groundnut", "wheat", "cumin", "castor", "onion", "chilli", "sugarcane",
         "mango", "pomegranate", "vegetables", "banana"]

# (system code, inquiry type, area in hectares, value band low..high in rupees)
SYSTEM_MIX: list[tuple[str, str, tuple[float, float], tuple[int, int]]] = [
    ("drip", "subsidised", (0.4, 2.0), (45_000, 180_000)),
    ("drip", "commercial", (1.0, 4.0), (90_000, 400_000)),
    ("mini_sprinkler", "subsidised", (0.4, 1.6), (35_000, 110_000)),
    ("sprinkler", "subsidised", (0.4, 2.0), (13_000, 35_000)),
    ("sprinkler", "commercial", (2.0, 5.0), (30_000, 70_000)),
    ("automation", "commercial", (2.0, 6.0), (60_000, 250_000)),
]

NOTES = [
    "Called, farmer wants a site visit next week after harvest.",
    "Visited the field. Water source is a bore well, 5 HP motor, about 2 km of main line needed.",
    "Farmer asked for the subsidy paperwork list; sent the checklist on WhatsApp.",
    "Comparing with a competitor quote. Wants lateral spacing 1.2 m for cotton.",
    "Design survey done. Two crops, drip inline, head unit at the well.",
    "Dealer will collect the 7/12 extract and Aadhaar copy on Monday.",
    "Farmer travelling; follow up after the 20th.",
    "Discussed a 45-day validity on the quote. He is waiting for the department's list.",
    "Second visit with the dealer. Quantity confirmed for 1.6 Ha.",
    "Wants the mini sprinkler on 8 m x 8 m spacing for groundnut.",
]

# Stage the pipeline lands in, weighted for a believable funnel.
STAGE_MIX = ["new"] * 14 + ["contacted"] * 18 + ["qualified"] * 14 + ["lost"] * 9
