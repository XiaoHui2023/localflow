function TextNode({ node }) {
  const className = [node.muted && "tpl-muted", node.bold && "tpl-bold"].filter(Boolean).join(" ");
  return <span className={className || undefined}>{node.text}</span>;
}

function BadgeNode({ node }) {
  return <span className={`tpl-badge tpl-tone-${node.tone}`}>{node.text}</span>;
}

function CodeNode({ node }) {
  if (!node.text) {
    return null;
  }
  return <pre className="tpl-code">{node.text}</pre>;
}

function LabeledNode({ node }) {
  return (
    <div className="tpl-labeled">
      <span className="tpl-label">{node.label}</span>
      <span className="tpl-value">{node.text}</span>
    </div>
  );
}

function SpacerNode({ node }) {
  return <span className={`tpl-spacer tpl-gap-${node.size}`} />;
}

function ChildrenNode({ node }) {
  return (
    <div className={`tpl-${node.kind} tpl-gap-${node.gap || "sm"}`}>
      {node.children.map((child, index) => (
        <TemplateView key={index} node={child} />
      ))}
    </div>
  );
}

function RowNode({ node }) {
  return (
    <div className={`tpl-row tpl-gap-${node.gap} tpl-align-${node.align}`}>
      {node.children.map((child, index) => (
        <TemplateView key={index} node={child} />
      ))}
    </div>
  );
}

function DivNode({ node }) {
  return (
    <div className={node.className ? `tpl-div ${node.className}` : "tpl-div"}>
      {node.children.map((child, index) => (
        <TemplateView key={index} node={child} />
      ))}
    </div>
  );
}

export default function TemplateView({ node }) {
  if (!node) {
    return null;
  }
  switch (node.kind) {
    case "text":
      return <TextNode node={node} />;
    case "badge":
      return <BadgeNode node={node} />;
    case "code":
      return <CodeNode node={node} />;
    case "labeled":
      return <LabeledNode node={node} />;
    case "spacer":
      return <SpacerNode node={node} />;
    case "row":
      return <RowNode node={node} />;
    case "col":
      return <ChildrenNode node={node} />;
    case "div":
      return <DivNode node={node} />;
    case "summary":
      return (
        <div className="tpl-summary">
          {node.children.map((child, index) => (
            <TemplateView key={index} node={child} />
          ))}
        </div>
      );
    case "detail":
      return (
        <div className="tpl-detail">
          {node.children.map((child, index) => (
            <TemplateView key={index} node={child} />
          ))}
        </div>
      );
    case "button":
      return (
        <button type="button" className="tpl-button" data-action={node.action}>
          {node.label}
        </button>
      );
    default:
      return <span className="tpl-unknown">{node.kind}</span>;
  }
}
