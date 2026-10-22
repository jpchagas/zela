import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";

/** Renders loading/error states for a query; returns null once data is ready. */
export function QueryState({ isLoading, error }: { isLoading: boolean; error: unknown }) {
  if (error) return <p className="text-destructive text-sm">{errorMessage(error)}</p>;
  if (isLoading)
    return (
      <div className="space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-2/3" />
      </div>
    );
  return null;
}
