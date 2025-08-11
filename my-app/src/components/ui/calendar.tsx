import { format } from "date-fns";

interface CalendarProps {
  selected?: Date;
  onSelect: (date: Date | undefined) => void;
}

function Calendar({ selected, onSelect }: CalendarProps) {
  return (
    <input
      type="date"
      value={selected ? format(selected, "yyyy-MM-dd") : ""}
      onChange={(e) =>
        onSelect(e.target.value ? new Date(e.target.value) : undefined)
      }
      className="rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    />
  );
}

export { Calendar };
