/**
 * Fictional reference data for the mock backend, shaped like the backend's showcase seed
 * (backend/scripts/showcase_data.py): Gujarat's real districts, codes and talukas; invented
 * villages, people and dealers. Ids are UUID-shaped, like the real API's, so mock ids pass
 * the same format checks.
 */

/** A stable UUID-shaped id: mockUuid(0x7e, 12) → "0000007e-0000-4000-8000-00000000000c". */
export function mockUuid(namespace: number, index: number): string {
  const head = namespace.toString(16).padStart(8, "0");
  const tail = index.toString(16).padStart(12, "0");
  return `${head}-0000-4000-8000-${tail}`;
}

/** Id namespaces, one per kind of record. */
export const MOCK_ID_SPACE = {
  territory: 0x7e,
  orgUnit: 0x0e,
  staff: 0x5f,
  partner: 0x9a,
  lead: 0x1ead,
  duplicate: 0xd0,
  lookup: 0x10,
  timeline: 0x71,
  quotation: 0x9707,
  approval: 0xa991,
  order: 0x0de7,
  orderLine: 0x0de1,
  dispatch: 0xd15,
} as const;

export const MOCK_STATE = { name: "Gujarat", code: "GJ" } as const;

/** The 33 districts with the abbreviations the client's sheets use. */
export const MOCK_DISTRICTS: readonly (readonly [name: string, code: string])[] = [
  ["Ahmedabad", "AMD"],
  ["Amreli", "AMR"],
  ["Anand", "AND"],
  ["Aravalli", "ARV"],
  ["Banaskantha", "BK"],
  ["Bharuch", "BHR"],
  ["Bhavnagar", "BVN"],
  ["Botad", "BTD"],
  ["Chhota Udepur", "CTU"],
  ["Dahod", "DH"],
  ["Dang", "DN"],
  ["Devbhumi Dwarka", "DBD"],
  ["Gandhinagar", "GN"],
  ["Gir Somnath", "GS"],
  ["Jamnagar", "JMN"],
  ["Junagadh", "JND"],
  ["Kheda", "KH"],
  ["Kutch", "KCT"],
  ["Mahisagar", "MH"],
  ["Mehsana", "MSN"],
  ["Morbi", "MRB"],
  ["Narmada", "NMD"],
  ["Navsari", "NVS"],
  ["Panchmahal", "PM"],
  ["Patan", "PTN"],
  ["Porbandar", "PBR"],
  ["Rajkot", "RJT"],
  ["Sabarkantha", "SK"],
  ["Surat", "SRT"],
  ["Surendranagar", "SNR"],
  ["Tapi", "TP"],
  ["Vadodara", "BRD"],
  ["Valsad", "VLD"],
];

/** District → taluka → villages. Three districts carry the field work, as in the showcase. */
export const MOCK_TALUKAS: Readonly<Record<string, Readonly<Record<string, readonly string[]>>>> = {
  Rajkot: {
    Gondal: ["Virpur", "Kolithad", "Shivrajpur", "Bhadar", "Vavdi"],
    Jetpur: ["Khirasara", "Nagalpar", "Devki Gadhda", "Pithadiya"],
    Jasdan: ["Atkot", "Vinchhiya Road", "Kamalapur", "Bhadla"],
    Dhoraji: ["Supedi", "Patanvav", "Bhukhi"],
    Upleta: ["Kolki", "Moti Panelii", "Bhayavadar"],
  },
  Junagadh: {
    Keshod: ["Balagam", "Ajab", "Mangrol Road"],
    Manavadar: ["Bantva", "Sardargadh", "Vadal"],
    Vanthali: ["Khorasa", "Sukhpur", "Dhandhusar"],
    Visavadar: ["Bhalchhel", "Kalsari", "Sanosari"],
  },
  Amreli: {
    Babra: ["Chamardi", "Jaliya", "Kotda Pitha"],
    Savarkundla: ["Vijpadi", "Thordi", "Dedan"],
    Dhari: ["Khambha Road", "Gopalgram", "Dalkhania"],
    Lathi: ["Damnagar", "Chavand", "Ansodar"],
  },
};

/** Districts with their own office; every other district is covered by the state office. */
export const MOCK_DISTRICT_OFFICES: Readonly<Record<string, string>> = {
  Rajkot: "Rajkot District",
  Junagadh: "Junagadh District",
  Amreli: "Amreli District",
};

export const MOCK_STATE_OFFICE = "Gujarat State";

/**
 * The one district no office covers in the mock, so the backend's
 * `territory_without_org_unit` refusal can be previewed from the New lead form.
 */
export const MOCK_UNCOVERED_DISTRICT = "Dang";

export const FIRST_NAMES = [
  "Ramesh",
  "Suresh",
  "Mahesh",
  "Jignesh",
  "Bhavesh",
  "Kiran",
  "Hitesh",
  "Pravin",
  "Dilip",
  "Nilesh",
  "Sanjay",
  "Vijay",
  "Kalpesh",
  "Arvind",
  "Harshad",
  "Meena",
  "Geeta",
  "Hansa",
  "Jyoti",
  "Kokila",
  "Anil",
  "Ganpat",
  "Devraj",
  "Mukesh",
  "Rajendra",
] as const;

export const LAST_NAMES = [
  "Patel",
  "Chaudhary",
  "Desai",
  "Rathod",
  "Parmar",
  "Solanki",
  "Jadeja",
  "Makwana",
  "Thakor",
  "Vasava",
  "Vaghela",
  "Radadiya",
  "Sojitra",
  "Dobariya",
  "Gohil",
  "Rabari",
  "Dabhi",
  "Bhalodiya",
  "Ahir",
  "Kathiriya",
] as const;

/** Staff who own leads. Invented people. */
export const MOCK_STAFF: readonly { readonly id: string; readonly full_name: string }[] = [
  "Aarav Desai",
  "Asha Patel",
  "Ravi Joshi",
  "Bharat Vaghela",
  "Kajal Solanki",
  "Nirav Shah",
].map((fullName, index) => ({ id: mockUuid(MOCK_ID_SPACE.staff, index + 1), full_name: fullName }));

/** Channel partners, by the district they work in. Invented businesses. */
export const MOCK_PARTNERS: readonly {
  readonly id: string;
  readonly name: string;
  readonly partner_type: string;
  readonly district: string;
}[] = [
  { name: "Saurashtra Agro Distributors", partner_type: "distributor", district: "Rajkot" },
  { name: "Sorath Agri Distributors", partner_type: "distributor", district: "Junagadh" },
  { name: "Shree Ganesh Agro Agency", partner_type: "dealer", district: "Rajkot" },
  { name: "Khodiyar Irrigation", partner_type: "dealer", district: "Rajkot" },
  { name: "Patel Agro Traders", partner_type: "dealer", district: "Junagadh" },
  { name: "Ambika Krishi Kendra", partner_type: "dealer", district: "Amreli" },
  { name: "Virpur Agro Point", partner_type: "sub_dealer", district: "Rajkot" },
  { name: "Balagam Krishi Seva", partner_type: "sub_dealer", district: "Junagadh" },
  { name: "Babra Farm Supplies", partner_type: "sub_dealer", district: "Amreli" },
].map((partner, index) => ({ ...partner, id: mockUuid(MOCK_ID_SPACE.partner, index + 1) }));

/** Short notes a salesperson leaves on a lost lead. */
export const LOST_NOTES = [
  "Went with a local installer at a lower price.",
  "Waiting for the subsidy portal to reopen; will revisit next season.",
  "Well water is not enough for drip on the whole plot.",
] as const;
