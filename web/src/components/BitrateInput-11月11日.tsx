import { useState } from "react";

const presets = ["6", "8", "10.5", "15", "25", "35"];

export function validVideoBitrate(value: string): boolean {
  return value === "" || (Number(value) >= 0.1 && Number(value) <= 1000);
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function BitrateInput({ value, onChange, disabled }: Props) {
  const [custom, setCustom] = useState(false);
  const selected = custom || (value !== "" && !presets.includes(value)) ? "custom" : value;
  return (
    <div className="bitrate-option">
      <label>
        视频码率
        <select aria-label="视频码率" value={selected} disabled={disabled} onChange={event => {
          const next = event.target.value;
          setCustom(next === "custom");
          onChange(next);
        }}>
          <option value="">默认画质</option>
          {presets.map(bitrate => <option key={bitrate} value={bitrate}>{bitrate} Mbps</option>)}
          <option value="custom">自定义</option>
        </select>
      </label>
      {selected === "custom" && <label>
        <input
          aria-label="自定义码率（Mbps）"
          aria-invalid={!validVideoBitrate(value)}
          type="number"
          min="0.1"
          max="1000"
          step="any"
          placeholder="输入码率"
          value={value === "custom" ? "" : value}
          disabled={disabled}
          onChange={event => onChange(event.target.value || "custom")}
        /> Mbps
      </label>}
    </div>
  );
}
