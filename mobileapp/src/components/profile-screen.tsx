import React, { useState } from "react";
import { Pressable, View, useColorScheme } from "react-native";
import { Text, Dialog } from "heroui-native";
import { router } from "expo-router";
import Animated, { ZoomIn, useReducedMotion } from "react-native-reanimated";

import { AppScreen } from "@/components/app-screen";
import { ProfileHero } from "@/components/profile-hero";
import { DashboardSkeleton } from "@/components/dashboard-skeleton";
import { DashboardError } from "@/components/dashboard-states";
import { humanize } from "@/components/status-chip";
import { Field, FieldGroup, OptionRow } from "@/components/auth/field-group";
import { Stagger } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Icon } from "@/components/icon";
import { useGet } from "@/hooks/use-api";
import { api, ApiError } from "@/lib/api";
import { getPalette } from "@/lib/theme";
import { useAuthStore } from "@/stores/auth-store";
import { useOrgStore } from "@/stores/org-store";
import { nameSchema, phoneSchema } from "@/lib/validations";
import type { MeResponse, MfaStatus, OrganizationOut, ProfileOut, ProfileUpdateRequest } from "@/types/api";

const ENROLLMENT_OPTIONS = [
  { value: "open", label: "Open", description: "Anyone with the code can join" },
  { value: "approved", label: "Approved", description: "Admins approve each signup" },
  { value: "invite_only", label: "Invite only", description: "Members join via email invite" },
] as const;

/**
 * Shared in-app profile screen for all three roles. Identity hero, grouped
 * editable contact sections in the iOS inset-field style (the login screen's
 * `FieldGroup`), your gym + security rows, and sign out (the one place the app
 * lets you leave — admin by default for owners).
 */
export function ProfileScreen() {
  const { user, clearSession } = useAuthStore();
  const { activeOrg } = useOrgStore();
  const isDark = useColorScheme() === "dark";
  const p = getPalette(isDark);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [signOutOpen, setSignOutOpen] = useState(false);

  const [gymName, setGymName] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [pendingEnrollment, setPendingEnrollment] = useState<string | null>(null);
  const [enrollError, setEnrollError] = useState<string | null>(null);
  const [savingEnrollment, setSavingEnrollment] = useState(false);

  const realtime = ["membership.changed", "gym_status.changed"];

  const me = useGet<MeResponse>("/auth/me", realtime);
  const profile = useGet<ProfileOut>("/auth/me/profile", realtime);
  const org = useGet<OrganizationOut>("/organizations/me", realtime);
  const mfa = useGet<MfaStatus>("/auth/mfa");

  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [city, setCity] = useState("");
  const [occupation, setOccupation] = useState("");
  const [education, setEducation] = useState("");
  const [emergency, setEmergency] = useState("");
  const [photoUrl, setPhotoUrl] = useState("");
  const [goals, setGoals] = useState("");
  const [healthNotes, setHealthNotes] = useState("");
  const [idType, setIdType] = useState("");
  const [idLast4, setIdLast4] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [prevProfile, setPrevProfile] = useState<ProfileOut | null | undefined>(profile.data);
  if (profile.data !== prevProfile) {
    setPrevProfile(profile.data);
    setFullName(profile.data?.full_name ?? "");
    setPhone(profile.data?.phone ?? "");
    setCity(profile.data?.city ?? "");
    setOccupation(profile.data?.occupation ?? "");
    setEducation(profile.data?.education ?? "");
    setEmergency(profile.data?.emergency_contact ?? "");
    setPhotoUrl(profile.data?.photo_url ?? "");
    setGoals(profile.data?.goals ?? "");
    setHealthNotes(profile.data?.health_notes ?? "");
    setIdType(profile.data?.id_document_type ?? "");
    setIdLast4(profile.data?.id_document_last4 ?? "");
  }

  const [prevOrg, setPrevOrg] = useState<OrganizationOut | null | undefined>(org.data);
  if (org.data !== prevOrg) {
    setPrevOrg(org.data);
    setGymName(org.data?.name ?? "");
  }

  const pristine =
    profile.data != null &&
    fullName === (profile.data.full_name ?? "") &&
    phone === (profile.data.phone ?? "") &&
    city === (profile.data.city ?? "") &&
    occupation === (profile.data.occupation ?? "") &&
    education === (profile.data.education ?? "") &&
    emergency === (profile.data.emergency_contact ?? "") &&
    (user?.role !== "member" || (
      photoUrl === (profile.data.photo_url ?? "") &&
      goals === (profile.data.goals ?? "") &&
      healthNotes === (profile.data.health_notes ?? "") &&
      idType === (profile.data.id_document_type ?? "") &&
      idLast4 === (profile.data.id_document_last4 ?? "")
    ));

  const clearFieldError = (field: string) => setFieldErrors((prev) => ({ ...prev, [field]: "" }));

  const openSignOut = () => {
    setError(null);
    setSignOutOpen(true);
  };

  const handleSignOut = () => {
    clearSession();
    router.replace("/");
  };

  const handleSave = async () => {
    setError(null);
    setSaved(false);
    const errs: Record<string, string> = {};
    if (!fullName.trim()) errs.full_name = "Name is required.";
    else if (!nameSchema.safeParse(fullName.trim()).success) errs.full_name = "Enter a valid name.";
    if (phone.trim() && !phoneSchema.safeParse(phone.trim()).success) errs.phone = "Enter a valid phone number.";

    if (Object.keys(errs).length) {
      setFieldErrors(errs);
      return;
    }
    setFieldErrors({});

    const body: ProfileUpdateRequest = {
      full_name: fullName.trim(),
      phone: phone.trim() || null,
      city: city.trim() || null,
      occupation: occupation.trim() || null,
      education: education.trim() || null,
      emergency_contact: emergency.trim() || null,
      ...(user?.role === "member" ? {
        photo_url: photoUrl.trim() || null,
        goals: goals.trim() || null,
        health_notes: healthNotes.trim() || null,
        id_document_type: idType.trim() || null,
        id_document_last4: idLast4.trim() || null,
      } : {}),
    };

    setSaving(true);
    try {
      await api.patch<ProfileOut>("/auth/me/profile", body);
      setSaved(true);
      profile.refetch();
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save your profile.");
    } finally {
      setSaving(false);
    }
  };

  const saveGymName = async () => {
    const trimmed = gymName.trim();
    if (trimmed === org.data?.name) return;
    if (!trimmed) {
      setNameError("Gym name is required.");
      return;
    }
    setNameError(null);
    setSavingName(true);
    try {
      await api.patch("/organizations/me/name", { name: trimmed });
      org.refetch();
    } catch (e) {
      setNameError(e instanceof ApiError ? e.message : "Could not update the gym name.");
    } finally {
      setSavingName(false);
    }
  };

  const openEnrollment = () => {
    setPendingEnrollment(org.data?.enrollment_mode ?? "open");
    setEnrollError(null);
    setEnrollOpen(true);
  };

  const applyEnrollment = async () => {
    const mode = pendingEnrollment ?? (org.data?.enrollment_mode ?? "open");
    if (mode === (org.data?.enrollment_mode ?? "open")) {
      setEnrollOpen(false);
      return;
    }
    setEnrollError(null);
    setSavingEnrollment(true);
    try {
      await api.patch("/organizations/me/enrollment", { enrollment_mode: mode });
      org.refetch();
      setEnrollOpen(false);
    } catch (e) {
      setEnrollError(e instanceof ApiError ? e.message : "Could not update enrollment.");
    } finally {
      setSavingEnrollment(false);
    }
  };

  const loading = profile.loading;
  const loadFailed = !loading && (profile.error || me.error || org.error);
  const reduceMotion = useReducedMotion();
  const isOwner = user?.role === "owner";

  const sections = profile.data && (
    <>
      <ProfileHero
        name={fullName || user?.full_name}
        email={profile.data.email}
        role={user?.role}
        memberStatus={me.data?.member_status}
        photoUrl={profile.data.photo_url}
      />

      <View className="mb-6">
        <FieldGroup title="Personal details">
          <Field
            label="Full name"
            placeholder="Your name"
            value={fullName}
            onChangeText={(t) => {
              setFullName(t);
              clearFieldError("full_name");
            }}
            autoCapitalize="words"
            autoComplete="name"
            error={fieldErrors.full_name}
          />
          <Field
            label="Phone"
            placeholder="+1 555 0123"
            value={phone}
            onChangeText={(t) => {
              setPhone(t);
              clearFieldError("phone");
            }}
            keyboardType="phone-pad"
            autoComplete="tel"
            error={fieldErrors.phone}
          />
          <Field label="City" placeholder="City" value={city} onChangeText={setCity} />
        </FieldGroup>
      </View>

      <View className="mb-6">
        <FieldGroup title="Work">
          <Field
            label="Occupation"
            placeholder="e.g. Personal trainer"
            value={occupation}
            onChangeText={setOccupation}
          />
          <Field
            label="Education"
            placeholder="e.g. Bachelor's degree"
            value={education}
            onChangeText={setEducation}
          />
        </FieldGroup>
      </View>

      <View className="mb-6">
        <FieldGroup title="Emergency contact">
          <Field
            label="Emergency contact"
            placeholder="Name & phone of emergency contact"
            value={emergency}
            onChangeText={setEmergency}
          />
        </FieldGroup>
      </View>

      {user?.role === "member" && (
        <View className="mb-6">
          <FieldGroup title="Membership profile" caption="Share only what you want your gym to know. Owners and managers can see your private health notes.">
            <Field label="Photo URL" placeholder="https://…" value={photoUrl} onChangeText={setPhotoUrl} autoCapitalize="none" keyboardType="url" />
            <Field label="Goals" placeholder="What are you working toward?" value={goals} onChangeText={setGoals} multiline maxLength={1000} />
            <Field label="Health notes" placeholder="Anything staff should know?" value={healthNotes} onChangeText={setHealthNotes} multiline maxLength={2000} />
            <Field label="ID document type" placeholder="Only if local rules permit" value={idType} onChangeText={setIdType} maxLength={60} />
            <Field label="ID final four" placeholder="Last 4 characters only" value={idLast4} onChangeText={setIdLast4} maxLength={4} autoCapitalize="characters" />
          </FieldGroup>
        </View>
      )}

      {error && (
        <View className="mb-4">
          <Alert type="error" message={error} onDismiss={() => setError(null)} />
        </View>
      )}

      <View className="mb-6">
        <Button onPress={handleSave} loading={saving} disabled={saving || pristine} className="w-full">
          {saved ? (
            <Animated.View
              entering={ZoomIn.springify().damping(14).stiffness(200)}
              className="flex-row items-center gap-1.5"
            >
              <Icon name="checkmark.circle.fill" android="check_circle" size={17} color="#ffffff" />
              <Text className="text-white" style={{ fontWeight: "600" }}>
                Saved
              </Text>
            </Animated.View>
          ) : (
            "Save changes"
          )}
        </Button>
      </View>

      {org.data && (
        <View className="mb-6">
          <FieldGroup title="Your gym">
            {isOwner ? (
              <>
                <Field
                  label="Gym name"
                  placeholder="Your gym's name"
                  value={gymName}
                  onChangeText={(t) => {
                    setGymName(t);
                    setNameError(null);
                  }}
                  autoCapitalize="words"
                  autoComplete="organization"
                  error={nameError ?? undefined}
                  trailing={
                    gymName.trim() !== (org.data?.name ?? "") ? (
                      <Pressable
                        onPress={saveGymName}
                        disabled={savingName}
                        hitSlop={10}
                        accessibilityRole="button"
                        accessibilityLabel="Save gym name"
                        className="active:opacity-50"
                      >
                        <View
                          className="h-8 w-8 items-center justify-center rounded-full"
                          style={{ backgroundColor: `${p.accent}1a` }}
                        >
                          <Icon name="checkmark" android="check" size={15} color={p.accent} weight="semibold" />
                        </View>
                      </Pressable>
                    ) : undefined
                  }
                />
                <OptionRow
                  label="Enrollment"
                  value={humanize(org.data.enrollment_mode ?? "open")}
                  onPress={openEnrollment}
                />
                <OptionRow
                  label="Rotate join code"
                  value={org.data.org_code}
                  onPress={() => router.navigate("/gym-settings/rotate-code")}
                />
                <OptionRow
                  label="Stripe payments"
                  value={humanize(org.data.stripe_connect_status ?? "none")}
                  onPress={() => router.navigate("/gym-settings/stripe")}
                />
              </>
            ) : (
              <>
                <ReadRow label="Gym" value={org.data.name} />
                <ReadRow label="Org code" value={org.data.org_code} />
                <ReadRow label="Enrollment" value={humanize(org.data.enrollment_mode ?? "open")} />
                <ReadRow label="Stripe" value={humanize(org.data.stripe_connect_status ?? "none")} />
              </>
            )}
          </FieldGroup>
        </View>
      )}

      <View className="mb-6">
        <FieldGroup title="Security">
          <OptionRow
            label="Password"
            value="Reset via email"
            onPress={() => router.navigate("/forgot-password")}
          />
          <OptionRow
            label="Multi-factor authentication"
            value={mfa.data ? (mfa.data.mfa_enabled ? "On" : "Off") : undefined}
            onPress={() => router.navigate("/mfa-enroll")}
          />
        </FieldGroup>
      </View>

      <View className="mb-6">
        <Button variant="danger" onPress={openSignOut} className="w-full">
          <View className="flex-row items-center justify-center gap-2">
            <Icon name="rectangle.portrait.and.arrow.right" android="logout" size={17} color="#ffffff" />
            <Text className="text-white" style={{ fontWeight: "600" }}>
              Sign out
            </Text>
          </View>
        </Button>
      </View>
    </>
  );

  return (
    <AppScreen title="Profile">
      {loading && !profile.data && <DashboardSkeleton />}

      {loadFailed && (
        <DashboardError
          message={profile.error ?? me.error ?? "Unable to load profile."}
          onRetry={() => {
            profile.refetch();
            me.refetch();
            org.refetch();
          }}
        />
      )}

      {!loadFailed && profile.data && (
        <>
          {reduceMotion ? sections : <Stagger gap={64}>{sections}</Stagger>}

          <Dialog isOpen={signOutOpen} onOpenChange={setSignOutOpen}>
            <Dialog.Portal>
              <Dialog.Overlay />
              <Dialog.Content>
                <Dialog.Close variant="ghost" />
                <View className="items-center pt-1">
                  <View
                    className="h-14 w-14 items-center justify-center rounded-full"
                    style={{ backgroundColor: `${p.danger}1a` }}
                  >
                    <Icon name="rectangle.portrait.and.arrow.right" android="logout" size={26} color={p.danger} />
                  </View>
                  <Dialog.Title className="mt-4 text-center">Sign out?</Dialog.Title>
                  <Dialog.Description className="text-center">
                    {`You'll need to sign back in to use ${activeOrg?.name ?? "this gym"}.`}
                  </Dialog.Description>
                </View>
                <View className="mt-5 flex-row gap-3">
                  <Button variant="ghost" size="sm" className="flex-1" onPress={() => setSignOutOpen(false)}>
                    Cancel
                  </Button>
                  <Button variant="danger" size="sm" className="flex-1" onPress={handleSignOut}>
                    Sign out
                  </Button>
                </View>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog>

          <Dialog isOpen={enrollOpen} onOpenChange={setEnrollOpen}>
            <Dialog.Portal>
              <Dialog.Overlay />
              <Dialog.Content>
                <Dialog.Close variant="ghost" />
                <View className="gap-5">
                  <View className="gap-1.5">
                    <Dialog.Title>Enrollment mode</Dialog.Title>
                    <Dialog.Description>
                      Choose how new members can join your gym.
                    </Dialog.Description>
                  </View>

                  <View className="overflow-hidden rounded-2xl bg-surface">
                    {ENROLLMENT_OPTIONS.map((opt, i) => {
                      const selected =
                        opt.value ===
                        (pendingEnrollment ?? (org.data?.enrollment_mode ?? "open"));
                      return (
                        <View key={opt.value}>
                          {i > 0 ? <View className="ml-4 h-px bg-border" /> : null}
                          <EnrollmentOption
                            label={opt.label}
                            description={opt.description}
                            selected={selected}
                            onPress={() => setPendingEnrollment(opt.value)}
                          />
                        </View>
                      );
                    })}
                  </View>

                  {enrollError ? (
                    <Alert type="error" message={enrollError} onDismiss={() => setEnrollError(null)} />
                  ) : null}

                  <Button
                    onPress={applyEnrollment}
                    loading={savingEnrollment}
                    disabled={
                      savingEnrollment ||
                      (pendingEnrollment ?? (org.data?.enrollment_mode ?? "open")) ===
                        (org.data?.enrollment_mode ?? "open")
                    }
                    className="w-full"
                  >
                    Done
                  </Button>
                </View>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog>
        </>
      )}
    </AppScreen>
  );
}

function ReadRow({ label, value }: { label: string; value: string }) {
  return (
    <View className="flex-row items-center px-4 py-3.5">
      <Text type="body" className="flex-1 text-foreground">
        {label}
      </Text>
      <Text type="body" color="muted" className="mr-1.5">
        {value}
      </Text>
    </View>
  );
}

function EnrollmentOption({
  label,
  description,
  selected,
  onPress,
}: {
  label: string;
  description: string;
  selected: boolean;
  onPress: () => void;
}) {
  const isDark = useColorScheme() === "dark";
  const p = getPalette(isDark);

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      accessibilityLabel={`${label}: ${description}`}
      className="flex-row items-center px-4 py-3.5 active:opacity-60"
      style={selected ? { backgroundColor: `${p.accent}0f` } : undefined}
    >
      <View className="flex-1 pr-3">
        <Text
          type="body"
          weight="semibold"
          style={{ color: selected ? p.accent : p.foreground }}
        >
          {label}
        </Text>
        <Text type="body-sm" color="muted" className="mt-0.5">
          {description}
        </Text>
      </View>
      <View
        className="h-6 w-6 items-center justify-center rounded-full"
        style={{
          backgroundColor: selected ? p.accent : "transparent",
          borderWidth: selected ? 0 : 1.5,
          borderColor: p.separator,
        }}
      >
        {selected ? (
          <Icon name="checkmark" android="check" size={14} weight="bold" color="#ffffff" />
        ) : null}
      </View>
    </Pressable>
  );
}
