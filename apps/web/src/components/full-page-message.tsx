import Image from "next/image";

export function FullPageMessage({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 p-6 text-center">
      <Image src="/zela-mark.png" alt="" width={48} height={48} priority />
      <h1 className="text-xl font-semibold">{title}</h1>
      {children && (
        <div className="text-muted-foreground flex max-w-sm flex-col items-center gap-4">
          {children}
        </div>
      )}
    </main>
  );
}
