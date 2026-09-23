import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default: "border-line bg-paper text-zinc-600",
        info: "border-navy-600/25 bg-navy-600/8 text-navy-600",
        success: "border-emerald-600/25 bg-emerald-50 text-emerald-700",
        warning: "border-amber-500/40 bg-amber-50 text-amber-800",
        danger: "border-red-500/30 bg-red-50 text-red-700",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}
