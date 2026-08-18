import { useId } from "react";
import { cx } from "../lib/cx";
import "./Field.css";

interface BaseProps {
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
}

interface TextFieldProps extends BaseProps {
  /** Characters the platform accepts. Shown as a counter and enforced. */
  max?: number;
  multiline?: boolean;
  placeholder?: string;
  rows?: number;
}

export function TextField({
  label,
  hint,
  value,
  onChange,
  max,
  multiline = false,
  placeholder,
  rows = 4,
}: TextFieldProps) {
  const id = useId();
  const near = max !== undefined && value.length >= max * 0.9;
  const shared = {
    id,
    value,
    placeholder,
    maxLength: max,
    className: "field__control",
    onChange: (event: { target: { value: string } }) => onChange(event.target.value),
  };

  return (
    <div className="field">
      <div className="field__head">
        <label className="field__label" htmlFor={id}>
          {label}
        </label>
        {max !== undefined && (
          <span className={cx("field__count", near && "field__count--near")}>
            {value.length}/{max}
          </span>
        )}
      </div>
      {multiline ? <textarea {...shared} rows={rows} /> : <input type="text" {...shared} />}
      {hint && <p className="field__hint">{hint}</p>}
    </div>
  );
}

interface SelectFieldProps extends BaseProps {
  options: readonly string[];
}

export function SelectField({ label, hint, value, onChange, options }: SelectFieldProps) {
  const id = useId();
  return (
    <div className="field">
      <div className="field__head">
        <label className="field__label" htmlFor={id}>
          {label}
        </label>
      </div>
      <select
        id={id}
        className="field__control"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      {hint && <p className="field__hint">{hint}</p>}
    </div>
  );
}
