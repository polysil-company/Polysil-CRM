import type { ConsentChannel, CustomerType } from "@/features/customers/api/customers.schemas";

export const CUSTOMER_TYPE_LABELS: Readonly<Record<CustomerType, string>> = {
  farmer: "Farmer",
  institution: "Institution",
  company: "Company",
};

export const CONSENT_CHANNEL_LABELS: Readonly<Record<ConsentChannel, string>> = {
  whatsapp: "On WhatsApp",
  form: "On a form",
  verbal: "Spoken",
  written: "In writing",
};
