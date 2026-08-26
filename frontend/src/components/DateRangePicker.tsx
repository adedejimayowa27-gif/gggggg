"use client";

import { useState } from "react";
import type { DateRangeValue } from "@/types";
import styles from "./DateRangePicker.module.css";

const PRESETS: { label: string; value: "today" | "7d" | "30d" | "90d" }[] = [
  { label: "Today", value: "today" },
  { label: "7d", value: "7d" },
  { label: "30d", value: "30d" },
  { label: "90d", value: "90d" },
];

interface Props {
  value: DateRangeValue;
  onChange: (value: DateRangeValue) => void;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function DateRangePicker({ value, onChange }: Props) {
  const isCustom = value.range === "custom";

  // Local text-field state for the custom inputs, seeded from the current
  // value (or today) so switching into "Custom" always shows a valid,
  // editable range instead of blank inputs.
  const [customStart, setCustomStart] = useState(
    value.range === "custom" ? value.start_date : todayIso()
  );
  const [customEnd, setCustomEnd] = useState(
    value.range === "custom" ? value.end_date : todayIso()
  );

  const handlePresetClick = (preset: "today" | "7d" | "30d" | "90d") => {
    onChange({ range: preset });
  };

  const handleCustomClick = () => {
    if (!isCustom) {
      onChange({ range: "custom", start_date: customStart, end_date: customEnd });
    }
  };

  const handleCustomDateChange = (field: "start" | "end", val: string) => {
    const nextStart = field === "start" ? val : customStart;
    const nextEnd = field === "end" ? val : customEnd;

    if (field === "start") setCustomStart(val);
    else setCustomEnd(val);

    if (nextStart && nextEnd && nextStart <= nextEnd) {
      onChange({ range: "custom", start_date: nextStart, end_date: nextEnd });
    }
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.presetGroup} role="group" aria-label="Date range">
        {PRESETS.map((p) => (
          <button
            key={p.value}
            type="button"
            className={`${styles.presetButton} ${
              value.range === p.value ? styles.presetButtonActive : ""
            }`}
            onClick={() => handlePresetClick(p.value)}
          >
            {p.label}
          </button>
        ))}
        <button
          type="button"
          className={`${styles.presetButton} ${isCustom ? styles.presetButtonActive : ""}`}
          onClick={handleCustomClick}
        >
          Custom
        </button>
      </div>

      {isCustom && (
        <div className={styles.customRow}>
          <input
            type="date"
            aria-label="Start date"
            className={styles.dateInput}
            value={customStart}
            max={customEnd}
            onChange={(e) => handleCustomDateChange("start", e.target.value)}
          />
          <span className={styles.customSep}>to</span>
          <input
            type="date"
            aria-label="End date"
            className={styles.dateInput}
            value={customEnd}
            min={customStart}
            onChange={(e) => handleCustomDateChange("end", e.target.value)}
          />
        </div>
      )}
    </div>
  );
}
