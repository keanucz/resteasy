import { Text, type TextProps } from 'react-native';

type Variant = 'body' | 'muted' | 'caption' | 'label' | 'subtitle' | 'title';

type AppTextProps = TextProps & {
  variant?: Variant;
};

const VARIANT_CLASSES: Record<Variant, string> = {
  body: 'font-sans text-base text-ink',
  muted: 'font-sans text-sm text-ink-muted',
  caption: 'font-sans text-xs text-ink-muted',
  label: 'font-sans-semibold text-xs uppercase tracking-widest text-ink-muted',
  subtitle: 'font-display text-xl text-ink',
  title: 'font-display text-3xl text-ink',
};

/** Text with the style guide's variants, in both colour schemes. Use instead of raw <Text>. */
export function AppText({ variant = 'body', className, ...rest }: AppTextProps) {
  return <Text className={`${VARIANT_CLASSES[variant]} ${className ?? ''}`} {...rest} />;
}
