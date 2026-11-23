import { Search01Icon } from "@hugeicons/core-free-icons";
import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Checkbox } from "./checkbox";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "./field";
import { Icon } from "./icon";
import { Input } from "./input";
import { InputGroup, InputGroupAddon, InputGroupInput } from "./input-group";
import { Kbd } from "./kbd";
import { Textarea } from "./textarea";

const CROPS = ["Cotton", "Banana", "Sugarcane", "Papaya"];

const meta = {
  title: "UI/Field",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

export const TextInput: Story = {
  render: () => (
    <Field className="w-80 max-w-full">
      <FieldLabel htmlFor="customer-name">Customer name</FieldLabel>
      <Input id="customer-name" autoComplete="name" placeholder="As on the land record" />
      <FieldDescription>Printed on quotations and subsidy forms.</FieldDescription>
    </Field>
  ),
};

/** The error is announced (role="alert") and linked to the input with aria-describedby. */
export const WithError: Story = {
  render: () => (
    <Field className="w-80 max-w-full" data-invalid="true">
      <FieldLabel htmlFor="mobile-invalid">Mobile number</FieldLabel>
      <InputGroup>
        <InputGroupAddon>
          <span className="text-sm text-muted-foreground">+91</span>
        </InputGroupAddon>
        <InputGroupInput
          id="mobile-invalid"
          inputMode="numeric"
          autoComplete="tel-national"
          defaultValue="98123"
          aria-invalid="true"
          aria-describedby="mobile-invalid-error"
        />
      </InputGroup>
      <FieldError id="mobile-invalid-error">Enter a 10-digit Indian mobile number.</FieldError>
    </Field>
  ),
};

export const SearchInput: Story = {
  render: () => (
    <InputGroup className="w-80 max-w-full">
      <InputGroupAddon>
        <Icon icon={Search01Icon} />
      </InputGroupAddon>
      <InputGroupInput type="search" placeholder="Search leads" aria-label="Search leads" />
      <InputGroupAddon align="end">
        <Kbd>/</Kbd>
      </InputGroupAddon>
    </InputGroup>
  ),
};

/** Grows with its content. */
export const Notes: Story = {
  render: () => (
    <Field className="w-80 max-w-full">
      <FieldLabel htmlFor="lead-notes">Notes</FieldLabel>
      <Textarea id="lead-notes" placeholder="Crop, acreage, water source, best time to call" />
    </Field>
  ),
};

export const Disabled: Story = {
  render: () => (
    <Field className="w-80 max-w-full" data-disabled="true">
      <FieldLabel htmlFor="lead-code">Lead code</FieldLabel>
      <Input id="lead-code" defaultValue="LD-10427" disabled />
      <FieldDescription>Generated when the lead is saved.</FieldDescription>
    </Field>
  ),
};

export const CheckboxGroup: Story = {
  render: () => (
    <FieldSet>
      <FieldLegend>Crops</FieldLegend>
      <FieldGroup className="gap-2.5">
        {CROPS.map((crop) => (
          <label key={crop} className="flex items-center gap-2.5 text-sm text-foreground">
            <Checkbox defaultChecked={crop === "Cotton"} />
            {crop}
          </label>
        ))}
      </FieldGroup>
      <FieldDescription>Every crop the system will irrigate.</FieldDescription>
    </FieldSet>
  ),
};
