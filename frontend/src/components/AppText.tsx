import { StyleSheet, Text, type TextProps } from 'react-native';

import { colors, fontSizes } from '@/constants/theme';

type Variant = 'body' | 'subtitle' | 'title';

type AppTextProps = TextProps & {
  variant?: Variant;
};

/** Text with themed variants. Use instead of raw <Text> so typography lives in one place. */
export function AppText({ variant = 'body', style, ...rest }: AppTextProps) {
  return <Text style={[styles.base, styles[variant], style]} {...rest} />;
}

const styles = StyleSheet.create({
  base: {
    color: colors.text,
  },
  body: {
    fontSize: fontSizes.body,
  },
  subtitle: {
    fontSize: fontSizes.subtitle,
    fontWeight: '600',
  },
  title: {
    fontSize: fontSizes.title,
    fontWeight: 'bold',
  },
});
