import { DetailSkeleton, HeaderSkeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <>
      <HeaderSkeleton />
      <DetailSkeleton />
    </>
  );
}
