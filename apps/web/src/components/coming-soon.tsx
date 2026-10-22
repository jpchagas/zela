import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";

export function ComingSoon({
  title,
  milestone,
  children,
}: {
  title: string;
  milestone: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <PageHeader title={title} />
      <Card className="border-dashed">
        <CardContent className="flex flex-col gap-3 py-8">
          <span className="bg-secondary w-fit rounded-full px-2.5 py-0.5 text-xs font-semibold">
            {milestone}
          </span>
          <div className="text-muted-foreground max-w-prose space-y-2 text-sm">{children}</div>
        </CardContent>
      </Card>
    </>
  );
}
