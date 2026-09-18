import { CircleX, TriangleAlert } from "lucide-react";
import { CopyValue } from "./CopyValue";
import { Hint } from "./Tooltip";

function InspectionValue({ item }) {
  const customText = item.name.startsWith("custom_text_");
  if (item.kind === "tokens" && Array.isArray(item.value)) {
    return (
      <div
        className="inspection-tokens"
        aria-label={`${item.label || item.name}：${item.value.length ? item.value.join("，") : "未配置"}`}
      >
        {item.value.length ? item.value.map((value, index) => (
          <span className="inspection-token" key={`${value}-${index}`}>{value}</span>
        )) : <span className="inspection-empty">未配置</span>}
      </div>
    );
  }
  if (item.kind === "code-list" && Array.isArray(item.value)) {
    return (
      <div className="inspection-code-list">
        {item.value.length ? item.value.map((value, index) => (
          <CopyValue value={value} key={`${value}-${index}`} />
        )) : <span className="inspection-empty">未配置</span>}
      </div>
    );
  }
  return <CopyValue value={item.value} customText={customText} />;
}

export function InspectionItems({ items, error }) {
  if (error)
    return (
      <div className="inspection-error" role="alert">
        <TriangleAlert />
        <span>{error}</span>
      </div>
    );
  if (!items.length) return null;
  return (
    <div className="inspection-grid">
      {items.map((item) => {
        const customText = item.name.startsWith("custom_text_");
        const unavailable =
          item.check === "availability" && item.severity === "error";
        return (
          <div
            className={`inspection-item severity-${item.severity}`}
            key={item.name}
            data-custom-text={customText || undefined}
          >
            {!customText && <span>{item.label || item.name}</span>}
            <InspectionValue item={item} />
            <span className="inspection-status-slot">
              {unavailable && (
                <Hint label={item.message || "不可用"}>
                  <button
                    type="button"
                    className="inspection-state"
                    aria-label="路径不存在"
                  >
                    <CircleX />
                  </button>
                </Hint>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}
