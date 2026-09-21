/**
 * Fictional reference data for the mock backend. Names and businesses are
 * invented; locations are real districts in Polysil's likely footprint.
 */

export const LOCATIONS = [
  { state: "Gujarat", district: "Vadodara", villages: ["Padra", "Savli", "Dabhoi", "Karjan"] },
  { state: "Gujarat", district: "Anand", villages: ["Borsad", "Petlad", "Umreth"] },
  { state: "Gujarat", district: "Rajkot", villages: ["Gondal", "Jetpur", "Dhoraji"] },
  { state: "Gujarat", district: "Banaskantha", villages: ["Deesa", "Palanpur", "Dhanera"] },
  { state: "Gujarat", district: "Junagadh", villages: ["Keshod", "Mangrol", "Visavadar"] },
  { state: "Maharashtra", district: "Jalgaon", villages: ["Raver", "Yawal", "Chopda"] },
  { state: "Maharashtra", district: "Nashik", villages: ["Niphad", "Dindori", "Pimpalgaon"] },
  { state: "Rajasthan", district: "Jalore", villages: ["Bhinmal", "Sanchore", "Raniwara"] },
  {
    state: "Madhya Pradesh",
    district: "Khargone",
    villages: ["Kasrawad", "Bhikangaon", "Maheshwar"],
  },
] as const;

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
  "Patil",
  "Pawar",
  "Choudhary",
  "Yadav",
  "Sharma",
  "Rabari",
  "Dabhi",
  "Gohil",
  "Bhil",
  "Mali",
] as const;

export const CROPS = [
  "Cotton",
  "Groundnut",
  "Banana",
  "Sugarcane",
  "Pomegranate",
  "Castor",
  "Cumin",
  "Wheat",
  "Onion",
  "Potato",
  "Papaya",
  "Mango",
] as const;

export const OWNERS = [
  { id: "emp-101", name: "Nirav Shah", avatarUrl: null },
  { id: "emp-102", name: "Pooja Mehta", avatarUrl: null },
  { id: "emp-103", name: "Rohit Joshi", avatarUrl: null },
  { id: "emp-104", name: "Asha Parikh", avatarUrl: null },
  { id: "emp-105", name: "Kunal Trivedi", avatarUrl: null },
  { id: "emp-106", name: "Farhan Qureshi", avatarUrl: null },
] as const;

export const CHANNEL_PARTNERS = [
  { id: "cp-201", name: "Shree Krishna Agro" },
  { id: "cp-202", name: "Jay Kisan Traders" },
  { id: "cp-203", name: "Narmada Irrigation Point" },
  { id: "cp-204", name: "Saurashtra Drip Solutions" },
  { id: "cp-205", name: "Khandesh Krishi Kendra" },
] as const;

export const LOST_REASONS = [
  "Price too high",
  "Chose a competitor",
  "Subsidy not approved",
  "No reliable water source",
  "Postponed to next season",
] as const;
