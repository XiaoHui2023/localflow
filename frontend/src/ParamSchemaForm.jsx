function TextParamField({ field, value, disabled, onChange }) {
  if (field.multiline) {
    return (
      <label className="var-field">
        <span className="var-label">{field.label}</span>
        <textarea
          rows={4}
          value={value ?? ""}
          disabled={disabled}
          onChange={(event) => onChange(field.name, event.target.value)}
        />
      </label>
    );
  }
  return (
    <label className="var-field">
      <span className="var-label">{field.label}</span>
      <input
        type="text"
        value={value ?? ""}
        disabled={disabled}
        onChange={(event) => onChange(field.name, event.target.value)}
      />
    </label>
  );
}

function NumberParamField({ field, value, disabled, onChange }) {
  return (
    <label className="var-field">
      <span className="var-label">{field.label}</span>
      <input
        type="number"
        value={value ?? field.default ?? 0}
        min={field.min}
        max={field.max}
        disabled={disabled}
        onChange={(event) => onChange(field.name, Number(event.target.value))}
      />
    </label>
  );
}

function BooleanParamField({ field, value, disabled, onChange }) {
  return (
    <label className="var-field var-field-check">
      <input
        type="checkbox"
        checked={Boolean(value)}
        disabled={disabled}
        onChange={(event) => onChange(field.name, event.target.checked)}
      />
      <span>{field.label}</span>
    </label>
  );
}

function CaseMatrixField({ field, value, disabled, onChange }) {
  const rows = Array.isArray(value) ? value : [];

  const updateRow = (id, patch) => {
    const next = rows.map((row) => (row.id === id ? { ...row, ...patch } : row));
    onChange(field.name, next);
  };

  return (
    <fieldset className="case-matrix">
      <legend>{field.label}</legend>
      <table className="case-matrix-table">
        <thead>
          <tr>
            <th>选用</th>
            <th>用例</th>
            <th>运行次数</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>
                <input
                  type="checkbox"
                  checked={Boolean(row.enabled)}
                  disabled={disabled}
                  onChange={(event) => updateRow(row.id, { enabled: event.target.checked })}
                />
              </td>
              <td>{row.label || row.id}</td>
              <td>
                <input
                  type="number"
                  className="case-runs-input"
                  min={1}
                  value={row.runs ?? 1}
                  disabled={disabled || !row.enabled}
                  onChange={(event) =>
                    updateRow(row.id, { runs: Math.max(1, Number(event.target.value) || 1) })
                  }
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </fieldset>
  );
}

export default function ParamSchemaForm({ schema, values, disabled, onChange }) {
  if (!schema || schema.length === 0) {
    return <p className="hint">无可编辑参数</p>;
  }

  return schema.map((field) => {
    const value = values[field.name];
    if (field.kind === "case_matrix") {
      return (
        <CaseMatrixField
          key={field.name}
          field={field}
          value={value}
          disabled={disabled}
          onChange={onChange}
        />
      );
    }
    if (field.kind === "boolean") {
      return (
        <BooleanParamField
          key={field.name}
          field={field}
          value={value}
          disabled={disabled}
          onChange={onChange}
        />
      );
    }
    if (field.kind === "number") {
      return (
        <NumberParamField
          key={field.name}
          field={field}
          value={value}
          disabled={disabled}
          onChange={onChange}
        />
      );
    }
    return (
      <TextParamField
        key={field.name}
        field={field}
        value={value}
        disabled={disabled}
        onChange={onChange}
      />
    );
  });
}
