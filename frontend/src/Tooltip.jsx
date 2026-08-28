import * as TooltipPrimitive from "@radix-ui/react-tooltip";

export function TooltipProvider({ children }) {
  return <TooltipPrimitive.Provider delayDuration={320} skipDelayDuration={180}>{children}</TooltipPrimitive.Provider>;
}

export function Hint({ children, label, content, side = "top", align = "center" }) {
  const text = label || content;
  if (!text) return children;
  return <TooltipPrimitive.Root><TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger><TooltipPrimitive.Portal><TooltipPrimitive.Content className="ui-tooltip" side={side} align={align} sideOffset={7} collisionPadding={8} avoidCollisions data-ui-overlay="tooltip"><span>{text}</span><TooltipPrimitive.Arrow className="ui-tooltip-arrow" width={9} height={5}/></TooltipPrimitive.Content></TooltipPrimitive.Portal></TooltipPrimitive.Root>;
}
