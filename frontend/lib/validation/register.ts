// Registration validation schemas (Zod).
//
// These mirror the backend Pydantic validators in
// backend/app/schemas/auth.py (OwnerRegisterStart). Keep the two in sync:
// the frontend gives instant feedback, the backend is the source of truth.
import { z } from "zod";

import { NAME_RE, CNIC_RE, PHONE_RE, emailField, collectErrors } from "./shared";

export { collectErrors };

const MIN_AGE = 16;
const MAX_AGE = 120;

function ageFrom(iso: string): number {
  const dob = new Date(iso);
  const now = new Date();
  let age = now.getFullYear() - dob.getFullYear();
  const m = now.getMonth() - dob.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < dob.getDate())) age--;
  return age;
}

const name = (label: string) =>
  z
    .string()
    .trim()
    .min(2, `${label} is too short`)
    .max(100, `${label} is too long`)
    .regex(NAME_RE, `Only letters, spaces, . ' and -`);

const password = z
  .string()
  .min(12, "At least 12 characters")
  .regex(/[a-z]/, "Needs lowercase")
  .regex(/[A-Z]/, "Needs uppercase")
  .regex(/[0-9]/, "Needs a number")
  .regex(/[^A-Za-z0-9]/, "Needs a symbol");

// Step 1 — account credentials.
export const accountSchema = z
  .object({
    email: emailField,
    password,
    confirm: z.string().min(1, "Confirm your password"),
  })
  .refine((d) => d.password === d.confirm, {
    message: "Passwords don't match",
    path: ["confirm"],
  });

// Step 2 — owner profile.
export const personalSchema = z.object({
  phone: z
    .string()
    .trim()
    .min(1, "Required")
    .transform((v) => v.replace(/[\s\-()]/g, ""))
    .pipe(z.string().regex(PHONE_RE, "Enter a valid phone number (7–15 digits)")),
  cnic: z
    .string()
    .trim()
    .min(1, "Required")
    .regex(CNIC_RE, "13 digits, e.g. 42101-1234567-8"),
  dateOfBirth: z
    .string()
    .min(1, "Required")
    .refine((v) => new Date(v) <= new Date(), "Cannot be in the future")
    .refine((v) => ageFrom(v) >= MIN_AGE, `You must be at least ${MIN_AGE}`)
    .refine((v) => ageFrom(v) <= MAX_AGE, "Enter a valid date of birth"),
  gender: z.enum(["male", "female", "other"], { message: "Required" }),
  occupation: z.string().trim().min(2, "Too short").max(100, "Too long"),
  education: z.string().trim().min(2, "Too short").max(100, "Too long"),
  address: z.string().trim().min(5, "Too short").max(200, "Too long"),
  city: name("City").max(85, "Too long"),
  emergencyContact: z.string().trim().min(5, "Too short").max(120, "Too long"),
});

export type AccountInput = z.infer<typeof accountSchema>;
export type PersonalInput = z.infer<typeof personalSchema>;
