import { useOutletContext } from "react-router-dom";
import { CaseDetailContext } from "../../views/CaseDetailView";
import { DetectionsPanel } from "../DetectionsPanel";
import { DetectionItem } from "../../types";
import { formatDate } from "../../utils/format";

export function DetectionsTab() {
    const {
        detections,
        loadingDetections,
        savingDetectionId,
        onUpdateDetection,
        onDeleteDetection,
        onCreateFinding,
        pushToast,
    } = useOutletContext<CaseDetailContext>();

    function handleEscalateToFinding(detection: DetectionItem) {
        const ruleId = String(detection.evidence_snapshot?.rule_id ?? "");
        const summary = String(detection.evidence_snapshot?.summary ?? "");
        const signalType = detection.signal_type;

        onCreateFinding({
            title: `${signalType}: ${ruleId}`,
            narrative: summary || `Escalated from detection ${detection.id}. Review evidence and add investigator analysis.`,
            severity: detection.severity as "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFORMATIONAL",
            confidence: "PROBABLE",
            signal_type: signalType,
            signal_rule_id: ruleId,
            detection_id: detection.id,
        });

        pushToast("success", `Finding created from ${ruleId || signalType}. Switch to the Findings tab to review.`);
    }

    return (
        <DetectionsPanel
            detections={detections}
            loadingDetections={loadingDetections}
            savingDetectionId={savingDetectionId}
            onUpdateDetection={onUpdateDetection}
            onDeleteDetection={onDeleteDetection}
            onEscalateToFinding={handleEscalateToFinding}
            formatDate={formatDate}
        />
    );
}
