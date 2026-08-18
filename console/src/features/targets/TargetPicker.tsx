import { OptionCard } from "../../components/OptionCard";
import { PLATFORM_LIST } from "../../domain/platforms";
import type { Platform } from "../../api/types";
import "./TargetPicker.css";

interface TargetPickerProps {
  selected: readonly Platform[];
  onToggle: (platform: Platform) => void;
  disabled?: boolean;
}

export function TargetPicker({ selected, onToggle }: TargetPickerProps) {
  return (
    <div className="targets">
      {PLATFORM_LIST.map((spec) => (
        <OptionCard
          key={spec.id}
          type="checkbox"
          checked={selected.includes(spec.id)}
          onChange={() => onToggle(spec.id)}
          title={spec.name}
          description={spec.summary}
          accent={spec.accent}
        />
      ))}
    </div>
  );
}
