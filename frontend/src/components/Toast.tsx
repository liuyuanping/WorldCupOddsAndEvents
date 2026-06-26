/* ── Toast Notification ──────────────────── */
import { useAppStore } from "../store/useAppStore";

export default function Toast() {
  const toastMsg = useAppStore((s) => s.toastMsg);
  if (!toastMsg) return null;
  return (
    <div className="toast">
      {toastMsg}
    </div>
  );
}
