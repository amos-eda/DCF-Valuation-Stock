import * as React from "react";
import { cn } from "@/lib/utils";

interface PopoverContextProps {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const PopoverContext = React.createContext<PopoverContextProps | null>(null);

function Popover({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  return (
    <PopoverContext.Provider value={{ open, setOpen }}>
      <div className="relative inline-block">{children}</div>
    </PopoverContext.Provider>
  );
}

function PopoverTrigger({ children }: { children: React.ReactElement }) {
  const ctx = React.useContext(PopoverContext);
  if (!ctx) return null;
  return React.cloneElement(children, {
    onClick: () => ctx.setOpen(!ctx.open),
  });
}

function PopoverContent({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const ctx = React.useContext(PopoverContext);
  if (!ctx || !ctx.open) return null;
  return (
    <div
      className={cn(
        "absolute z-50 mt-2 rounded-md border bg-popover p-2 text-popover-foreground shadow-md",
        className
      )}
    >
      {children}
    </div>
  );
}

export { Popover, PopoverTrigger, PopoverContent };
