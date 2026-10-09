import type { QrCodeWire } from "@/features/lead-capture/api/lead-capture.schemas";

import { MOCK_ID_SPACE, MOCK_PARTNERS, mockUuid } from "./reference";
import { MOCK_TERRITORIES } from "./territories";

/** Where the mock's codes point: the enquiry page on this app. */
export function mockEnquiryUrl(code: string): string {
  const origin = typeof window === "undefined" ? "http://localhost:3000" : window.location.origin;
  return `${origin}/enquiry?qr=${code}`;
}

/** Six characters with no look-alikes (no 0/O, 1/I/L), as the backend makes them. */
const CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ";

export function mockQrCode(serial: number): string {
  let value = serial * 7919 + 104_729;
  let code = "";
  for (let index = 0; index < 6; index += 1) {
    code += CODE_ALPHABET[value % CODE_ALPHABET.length] ?? "X";
    value = Math.floor(value / CODE_ALPHABET.length) + serial * 31;
  }
  return code;
}

/** LEAD-013 · Three printed codes: a dealer's counter, a fair stall, a switched-off leaflet. */
export function seedQrCodes(): QrCodeWire[] {
  const partner = MOCK_PARTNERS[0];
  const taluka = MOCK_TERRITORIES.find((territory) => territory.level === "taluka");
  const rows: {
    label: string;
    campaign: string | null;
    withPartner: boolean;
    active: boolean;
    leads: number;
    days: number;
  }[] = [
    {
      label: "Counter at the dealer",
      campaign: "Kharif 2026",
      withPartner: true,
      active: true,
      leads: 14,
      days: 40,
    },
    {
      label: "Krishi Mela stall, Rajkot",
      campaign: "Krishi Mela 2026",
      withPartner: false,
      active: true,
      leads: 31,
      days: 18,
    },
    {
      label: "Drip leaflet, first print",
      campaign: null,
      withPartner: false,
      active: false,
      leads: 6,
      days: 120,
    },
  ];
  return rows.map((row, index) => {
    const code = mockQrCode(index + 1);
    return {
      id: mockUuid(MOCK_ID_SPACE.qrCode, index + 1),
      code,
      url: mockEnquiryUrl(code),
      label: row.withPartner && partner !== undefined ? `${row.label}: ${partner.name}` : row.label,
      campaign: row.campaign,
      partner:
        row.withPartner && partner !== undefined
          ? { id: partner.id, name: partner.name, partner_type: partner.partner_type }
          : null,
      territory:
        row.withPartner && taluka !== undefined
          ? { id: taluka.id, name: taluka.name, level: taluka.level }
          : null,
      is_active: row.active,
      lead_count: row.leads,
      created_at: new Date(Date.UTC(2026, 9, 4) - row.days * 86_400_000).toISOString(),
    };
  });
}
