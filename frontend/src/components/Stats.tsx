import type { ReactNode } from 'react';
import { Pressable, Text, View } from 'react-native';

type StatTileProps = {
  label: string;
  value: string;
  /** A short line under the value: "since bedtime". */
  detail?: string;
};

/** Small label over a big value. Lay several out in a `flex-row gap-2.5` row. */
export function StatTile({ label, value, detail }: StatTileProps) {
  return (
    <View className="flex-1 gap-2 rounded-2xl bg-surface p-3.5">
      <Text className="font-sans text-xs text-ink-muted">{label}</Text>
      <Text className="font-sans-semibold text-xl text-ink">{value}</Text>
      {detail ? <Text className="-mt-1 font-sans text-xs text-ink-muted">{detail}</Text> : null}
    </View>
  );
}

type SummaryCardProps = {
  /** A short heading, usually with one <StatusWord>: "A quiet night". */
  heading: ReactNode;
  /** The night written as a sentence. */
  body: string;
};

/** Summary written as words rather than numbers. */
export function SummaryCard({ heading, body }: SummaryCardProps) {
  return (
    <View className="gap-2 rounded-2xl bg-surface p-3.5">
      <Text className="font-display text-xl text-ink">{heading}</Text>
      <Text className="font-sans text-base leading-6 text-ink">{body}</Text>
    </View>
  );
}

type DataTableProps = {
  columns: readonly string[];
  /** Cells are strings or nodes (for example a <StatusWord>). */
  rows: readonly (readonly ReactNode[])[];
  /** Makes each row a button, e.g. to open that night. */
  onRowPress?: (row: number) => void;
  /** Read out for each pressable row. */
  rowLabel?: (row: number) => string;
};

/** Striped table: every other row sits on a surface band. The first column is bold. */
export function DataTable({ columns, rows, onRowPress, rowLabel }: DataTableProps) {
  return (
    <View accessibilityRole="list">
      <View className="flex-row px-3 pb-1.5">
        {columns.map((column) => (
          <Text key={column} className="flex-1 font-sans-semibold text-[11px] uppercase tracking-widest text-ink-muted">
            {column}
          </Text>
        ))}
      </View>
      {rows.map((cells, r) => {
        const band = `flex-row items-center rounded-lg px-3 py-2.5 ${r % 2 === 0 ? 'bg-surface' : ''}`;
        const content = cells.map((cell, c) => (
          <View key={c} className="flex-1">
            {typeof cell === 'string' ? (
              <Text className={`${c === 0 ? 'font-sans-semibold' : 'font-sans'} text-sm text-ink`}>{cell}</Text>
            ) : (
              cell
            )}
          </View>
        ));
        return onRowPress ? (
          <Pressable
            key={r}
            accessibilityRole="button"
            accessibilityLabel={rowLabel?.(r)}
            onPress={() => onRowPress(r)}
            className={`${band} min-h-11 active:opacity-70`}
          >
            {content}
          </Pressable>
        ) : (
          <View key={r} className={band}>
            {content}
          </View>
        );
      })}
    </View>
  );
}
