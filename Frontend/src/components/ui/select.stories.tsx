import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import type * as React from "react";

import { Field, FieldDescription, FieldLabel } from "./field";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectGroupLabel,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./select";

interface Option {
  value: string;
  label: string;
}

const DISTRICTS: Option[] = [
  { value: "vadodara", label: "Vadodara" },
  { value: "anand", label: "Anand" },
  { value: "kheda", label: "Kheda" },
  { value: "bharuch", label: "Bharuch" },
  { value: "panchmahal", label: "Panchmahal" },
];

const SOURCES_ONLINE: Option[] = [
  { value: "whatsapp", label: "WhatsApp" },
  { value: "website", label: "Website" },
  { value: "qr_code", label: "QR code" },
];

const SOURCES_OFFLINE: Option[] = [
  { value: "employee", label: "Field staff" },
  { value: "phone_email", label: "Phone or email" },
  { value: "offline", label: "Walk-in" },
];

function DistrictSelect({
  id,
  size = "md",
  disabled = false,
  defaultValue = null,
}: {
  id: string;
  size?: "sm" | "md";
  disabled?: boolean;
  defaultValue?: string | null;
}): React.JSX.Element {
  return (
    <Field className="w-64">
      <FieldLabel htmlFor={id}>District</FieldLabel>
      <Select items={DISTRICTS} defaultValue={defaultValue} disabled={disabled}>
        <SelectTrigger id={id} size={size}>
          <SelectValue placeholder="Choose a district" />
        </SelectTrigger>
        <SelectContent>
          {DISTRICTS.map((district) => (
            <SelectItem key={district.value} value={district.value}>
              {district.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

const meta = {
  title: "UI/Select",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => <DistrictSelect id="district-default" defaultValue="vadodara" />,
};

export const Placeholder: Story = {
  render: () => <DistrictSelect id="district-placeholder" />,
};

export const Small: Story = {
  render: () => <DistrictSelect id="district-small" size="sm" defaultValue="anand" />,
};

export const Disabled: Story = {
  render: () => <DistrictSelect id="district-disabled" disabled defaultValue="kheda" />,
};

export const Grouped: Story = {
  render: () => (
    <Field className="w-64">
      <FieldLabel htmlFor="lead-source">Lead source</FieldLabel>
      <Select items={[...SOURCES_ONLINE, ...SOURCES_OFFLINE]} defaultValue="whatsapp">
        <SelectTrigger id="lead-source">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectGroupLabel>Online</SelectGroupLabel>
            {SOURCES_ONLINE.map((source) => (
              <SelectItem key={source.value} value={source.value}>
                {source.label}
              </SelectItem>
            ))}
          </SelectGroup>
          <SelectGroup>
            <SelectGroupLabel>Offline</SelectGroupLabel>
            {SOURCES_OFFLINE.map((source) => (
              <SelectItem key={source.value} value={source.value}>
                {source.label}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
      <FieldDescription>Where the customer first reached us.</FieldDescription>
    </Field>
  ),
};
