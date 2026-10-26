"use client";

import { Input } from "@/components/ui";
import { Row, ReadValue } from "@/components/settings/primitives";
import type { ProfileOut } from "@/lib/types";

/* The profile fields are shared: the standalone /app/account page owns and
   saves them itself, while the settings dialog stages them under its single
   global Save bar. Keeping one field implementation is what stops the two
   surfaces from drifting. */
export interface AccountFieldsValue {
  full_name: string;
  phone: string;
  address: string;
  city: string;
  occupation: string;
  education: string;
  emergency_contact: string;
}

export const emptyAccountFields: AccountFieldsValue = {
  full_name: "",
  phone: "",
  address: "",
  city: "",
  occupation: "",
  education: "",
  emergency_contact: "",
};

export function AccountFields({
  value,
  onChange,
  profile,
}: {
  value: AccountFieldsValue;
  onChange: (patch: Partial<AccountFieldsValue>) => void;
  profile: ProfileOut | null;
}) {
  return (
    <>
      <Row label="Email" description="Email cannot be changed here">
        <ReadValue>{profile?.email ?? "—"}</ReadValue>
      </Row>
      <Row label="Full name" description="Your display name across the platform">
        <Input size="sm" value={value.full_name} onChange={(e) => onChange({ full_name: e.target.value })} placeholder="Your name" />
      </Row>
      <Row label="Phone" description="Used for account recovery and alerts">
        <Input size="sm" value={value.phone} onChange={(e) => onChange({ phone: e.target.value })} placeholder="+1 555-0123" />
      </Row>
      <Row label="Address" description="Your street address">
        <Input size="sm" value={value.address} onChange={(e) => onChange({ address: e.target.value })} placeholder="Street address" />
      </Row>
      <Row label="City" description="Your city">
        <Input size="sm" value={value.city} onChange={(e) => onChange({ city: e.target.value })} placeholder="City" />
      </Row>
      <Row label="Occupation" description="What you do">
        <Input size="sm" value={value.occupation} onChange={(e) => onChange({ occupation: e.target.value })} placeholder="e.g. Personal trainer" />
      </Row>
      <Row label="Education" description="Your highest qualification">
        <Input size="sm" value={value.education} onChange={(e) => onChange({ education: e.target.value })} placeholder="e.g. Bachelor's degree" />
      </Row>
      <Row label="Emergency contact" description="Who to reach in an emergency">
        <Input size="sm" value={value.emergency_contact} onChange={(e) => onChange({ emergency_contact: e.target.value })} placeholder="Name & phone" />
      </Row>
      {profile?.gender && (
        <Row label="Gender" description="Set during onboarding">
          <ReadValue>{profile.gender}</ReadValue>
        </Row>
      )}
      {profile?.date_of_birth && (
        <Row label="Date of birth" description="Set during onboarding">
          <ReadValue>{profile.date_of_birth}</ReadValue>
        </Row>
      )}
    </>
  );
}
