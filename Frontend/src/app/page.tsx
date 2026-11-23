import { redirect } from "next/navigation";

// TODO(SITE-001): the public website (information, Product Master, phone-number entry) will live at "/".
export default function HomePage(): never {
  redirect("/dashboard");
}
