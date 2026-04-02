import { useState } from "react";
import { NewReferralPayload, ReferralItem, ReferralStatus, ReferralUpdatePayload } from "../types";
import { Button } from "./ui/Button";
import { EmptyState } from "./ui/EmptyState";
import { FormInput } from "./ui/FormInput";
import { FormSelect } from "./ui/FormSelect";
import { FormTextarea } from "./ui/FormTextarea";
import styles from "./ReferralsPanel.module.css";

const REFERRAL_STATUS_LABELS: Record<ReferralStatus, string> = {
    DRAFT: "Draft",
    SUBMITTED: "Submitted",
    ACKNOWLEDGED: "Acknowledged",
    CLOSED: "Closed",
};

const STATUS_TRANSITIONS: ReferralStatus[] = ["DRAFT", "SUBMITTED", "ACKNOWLEDGED", "CLOSED"];

interface ReferralsPanelProps {
    referrals: ReferralItem[];
    loadingReferrals: boolean;
    savingReferralId: number | null;
    onCreateReferral: (payload: NewReferralPayload) => void;
    onUpdateReferral: (referralId: number, payload: ReferralUpdatePayload) => void;
    onDeleteReferral: (referralId: number) => void;
    formatDate: (value: string) => string;
}

interface NewReferralForm {
    agency_name: string;
    submission_id: string;
    contact_alias: string;
    notes: string;
}

const EMPTY_FORM: NewReferralForm = {
    agency_name: "",
    submission_id: "",
    contact_alias: "",
    notes: "",
};

export function ReferralsPanel({
    referrals,
    loadingReferrals,
    savingReferralId,
    onCreateReferral,
    onUpdateReferral,
    onDeleteReferral,
    formatDate,
}: ReferralsPanelProps) {
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState<NewReferralForm>(EMPTY_FORM);
    const [formError, setFormError] = useState<string | null>(null);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [editDraft, setEditDraft] = useState<ReferralUpdatePayload>({});

    function handleFormChange(field: keyof NewReferralForm, value: string) {
        setForm((prev) => ({ ...prev, [field]: value }));
        if (formError) setFormError(null);
    }

    function handleSubmitNew() {
        const agencyName = form.agency_name.trim();
        if (!agencyName) {
            setFormError("Agency name is required.");
            return;
        }
        onCreateReferral({
            agency_name: agencyName,
            submission_id: form.submission_id.trim() || undefined,
            contact_alias: form.contact_alias.trim() || undefined,
            notes: form.notes.trim() || undefined,
        });
        setForm(EMPTY_FORM);
        setShowForm(false);
        setFormError(null);
    }

    function handleStartEdit(referral: ReferralItem) {
        setEditingId(referral.referral_id);
        setEditDraft({
            agency_name: referral.agency_name,
            submission_id: referral.submission_id,
            contact_alias: referral.contact_alias,
            notes: referral.notes,
            status: referral.status,
        });
    }

    function handleSaveEdit(referralId: number) {
        onUpdateReferral(referralId, editDraft);
        setEditingId(null);
        setEditDraft({});
    }

    function handleCancelEdit() {
        setEditingId(null);
        setEditDraft({});
    }

    return (
        <div className={styles.referralsPanel}>
            <div className={styles.referralsPanelHeader}>
                <h3>Government Referrals</h3>
                {!showForm && (
                    <Button variant="primary" onClick={() => setShowForm(true)}>
                        + New Referral
                    </Button>
                )}
            </div>

            {showForm && (
                <div className={`${styles.referralForm} ${styles.card}`}>
                    <h4>New Referral</h4>
                    <div className={styles.formRow}>
                        <label>Agency Name *</label>
                        <FormInput
                            value={form.agency_name}
                            onChange={(e) => handleFormChange("agency_name", e.target.value)}
                            placeholder="e.g. FBI, IRS, State AG"
                        />
                        {formError && <span className="field-error">{formError}</span>}
                    </div>
                    <div className={styles.formRow}>
                        <label>Submission ID</label>
                        <FormInput
                            value={form.submission_id}
                            onChange={(e) => handleFormChange("submission_id", e.target.value)}
                            placeholder="Agency tracking number (optional)"
                        />
                    </div>
                    <div className={styles.formRow}>
                        <label>Contact Alias</label>
                        <FormInput
                            value={form.contact_alias}
                            onChange={(e) => handleFormChange("contact_alias", e.target.value)}
                            placeholder="Internal alias for contact (optional)"
                        />
                    </div>
                    <div className={styles.formRow}>
                        <label>Notes</label>
                        <FormTextarea
                            value={form.notes}
                            onChange={(e) => handleFormChange("notes", e.target.value)}
                            placeholder="Additional context (optional)"
                            rows={3}
                        />
                    </div>
                    <div className={styles.formActions}>
                        <Button variant="primary" onClick={handleSubmitNew}>
                            Create Referral
                        </Button>
                        <Button
                            onClick={() => {
                                setShowForm(false);
                                setForm(EMPTY_FORM);
                                setFormError(null);
                            }}
                        >
                            Cancel
                        </Button>
                    </div>
                </div>
            )}

            {loadingReferrals && (
                <p className={styles.loadingHint}>Loading referrals…</p>
            )}

            {!loadingReferrals && referrals.length === 0 && !showForm && (
                <EmptyState
                    title="No referrals yet"
                    detail="Create a referral to track submissions to government agencies."
                />
            )}

            {referrals.map((referral) => {
                const isSaving = savingReferralId === referral.referral_id;
                const isEditing = editingId === referral.referral_id;

                return (
                    <div key={referral.referral_id} className={`${styles.referralCard} ${styles.card}`}>
                        {isEditing ? (
                            <div className={styles.referralEdit}>
                                <div className={styles.formRow}>
                                    <label>Agency Name *</label>
                                    <FormInput
                                        value={editDraft.agency_name ?? ""}
                                        onChange={(e) =>
                                            setEditDraft((d) => ({ ...d, agency_name: e.target.value }))
                                        }
                                    />
                                </div>
                                <div className={styles.formRow}>
                                    <label>Submission ID</label>
                                    <FormInput
                                        value={editDraft.submission_id ?? ""}
                                        onChange={(e) =>
                                            setEditDraft((d) => ({ ...d, submission_id: e.target.value }))
                                        }
                                    />
                                </div>
                                <div className={styles.formRow}>
                                    <label>Contact Alias</label>
                                    <FormInput
                                        value={editDraft.contact_alias ?? ""}
                                        onChange={(e) =>
                                            setEditDraft((d) => ({ ...d, contact_alias: e.target.value }))
                                        }
                                    />
                                </div>
                                <div className={styles.formRow}>
                                    <label>Status</label>
                                    <FormSelect
                                        value={editDraft.status ?? referral.status}
                                        onChange={(e) =>
                                            setEditDraft((d) => ({
                                                ...d,
                                                status: e.target.value as ReferralStatus,
                                            }))
                                        }
                                    >
                                        {STATUS_TRANSITIONS.map((s) => (
                                            <option key={s} value={s}>
                                                {REFERRAL_STATUS_LABELS[s]}
                                            </option>
                                        ))}
                                    </FormSelect>
                                </div>
                                <div className={styles.formRow}>
                                    <label>Notes</label>
                                    <FormTextarea
                                        value={editDraft.notes ?? ""}
                                        onChange={(e) =>
                                            setEditDraft((d) => ({ ...d, notes: e.target.value }))
                                        }
                                        rows={3}
                                    />
                                </div>
                                <div className={styles.formActions}>
                                    <Button
                                        variant="primary"
                                        disabled={isSaving}
                                        onClick={() => handleSaveEdit(referral.referral_id)}
                                    >
                                        {isSaving ? "Saving…" : "Save"}
                                    </Button>
                                    <Button onClick={handleCancelEdit}>Cancel</Button>
                                </div>
                            </div>
                        ) : (
                            <div className={styles.referralView}>
                                <div className={styles.referralRow}>
                                    <strong>{referral.agency_name || "Unknown Agency"}</strong>
                                    <span className={`${styles.referralStatus} ${
                                        referral.status === "DRAFT" ? styles.referralStatusDraft :
                                        referral.status === "SUBMITTED" ? styles.referralStatusSubmitted :
                                        referral.status === "ACKNOWLEDGED" ? styles.referralStatusAcknowledged :
                                        referral.status === "CLOSED" ? styles.referralStatusClosed : ""
                                    }`}>
                                        {REFERRAL_STATUS_LABELS[referral.status]}
                                    </span>
                                </div>
                                {referral.submission_id && (
                                    <div className={styles.referralMeta}>
                                        Ref: {referral.submission_id}
                                    </div>
                                )}
                                {referral.contact_alias && (
                                    <div className={styles.referralMeta}>
                                        Contact: {referral.contact_alias}
                                    </div>
                                )}
                                {referral.notes && (
                                    <div className={styles.referralNotes}>{referral.notes}</div>
                                )}
                                <div className={`${styles.referralMeta} ${styles.referralDate}`}>
                                    Filed: {formatDate(referral.filing_date)}
                                </div>
                                <div className={styles.referralActions}>
                                    <Button onClick={() => handleStartEdit(referral)}>Edit</Button>
                                    <Button
                                        disabled={isSaving}
                                        onClick={() => onDeleteReferral(referral.referral_id)}
                                    >
                                        Delete
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
