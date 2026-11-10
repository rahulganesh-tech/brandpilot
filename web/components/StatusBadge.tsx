import { STATUS_LABEL } from "@/lib/api";
import type { ScanStatus } from "@/lib/types";

const STYLE: Record<ScanStatus, string> = {
  draft: "bg-desk text-ink",
  in_review: "bg-[#e7ebff] text-accent",
  approved: "bg-[#e3f4e6] text-ok",
  sent_back: "bg-[#fde7ee] text-high",
};

export function StatusBadge({ status }: { status: ScanStatus }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${STYLE[status]}`}>
      {STATUS_LABEL[status]}
    </span>
  );
}
