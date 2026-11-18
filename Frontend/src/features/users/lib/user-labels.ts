import type { UserRow, UserType } from "@/features/users/api/users.schemas";
import { formatIndianPhone } from "@/lib/format";

/** ADMN-001 · How a person reads on screen. */

export const USER_TYPE_LABELS: Readonly<Record<UserType, string>> = {
  staff: "Staff",
  partner_user: "Partner user",
};

/** "Rajkot District" for staff, the partner's name for a partner user. */
export function anchorOf(user: Pick<UserRow, "office" | "partner">): string {
  if (user.office !== null) return user.office.name;
  if (user.partner !== null) return user.partner.name ?? "A partner outside your scope";
  return "No office";
}

/** How the person signs in: their email, or their mobile for a partner user. */
export function signInIdOf(user: Pick<UserRow, "userType" | "email" | "mobile">): string {
  if (user.userType === "staff") return user.email ?? "No email";
  return user.mobile === null ? "No mobile" : formatIndianPhone(`+${user.mobile}`);
}

/** The mobile as people read it; the API stores 91XXXXXXXXXX without the plus. */
export function mobileText(mobile: string | null): string | null {
  return mobile === null ? null : formatIndianPhone(`+${mobile}`);
}
