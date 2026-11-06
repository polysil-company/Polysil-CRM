import type { Message, Person } from "@/features/messages/api/messages.schemas";
import { formatDate, formatTime, isSameDay } from "@/lib/format";

const DAY_MS = 24 * 60 * 60 * 1000;
const GROUP_GAP_MS = 5 * 60 * 1000;

/** Conversation list: "4:05 pm" for today, "14 Sept" before that. */
export function formatConversationTime(value: string, now: Date): string {
  return isSameDay(value, now) ? formatTime(value) : formatDate(value, now);
}

/** Divider between days in a thread: "Today", "Yesterday" or "14 Sept". */
export function formatDayLabel(value: string, now: Date): string {
  if (isSameDay(value, now)) {
    return "Today";
  }
  if (isSameDay(value, new Date(now.getTime() - DAY_MS))) {
    return "Yesterday";
  }
  return formatDate(value, now);
}

/** "District Manager · Vadodara District" */
export function describePerson(person: Person): string {
  return [person.roleName, person.orgUnitName].filter((part) => part !== null).join(" · ");
}

/** Whether `next` reads as part of the same burst as `previous`: same sender, day and five minutes. */
export function continuesGroup(previous: Message | undefined, next: Message | undefined): boolean {
  if (previous === undefined || next === undefined) {
    return false;
  }
  return (
    previous.senderId === next.senderId &&
    isSameDay(previous.createdAt, next.createdAt) &&
    Date.parse(next.createdAt) - Date.parse(previous.createdAt) < GROUP_GAP_MS
  );
}
