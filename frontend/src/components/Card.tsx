import type { PropsWithChildren } from 'react';
import { View } from 'react-native';

type CardProps = PropsWithChildren<{ className?: string }>;

/** Raised surface for grouped content. */
export function Card({ className, children }: CardProps) {
  return <View className={`gap-2.5 rounded-card bg-surface p-[18px] ${className ?? ''}`}>{children}</View>;
}
