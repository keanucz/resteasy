import { AppText } from '@/components/AppText';
import { Screen } from '@/components/Screen';

/** Home route ("/", signed in only): a placeholder that confirms the login worked. */
export default function HomeScreen() {
  return (
    <Screen>
      <AppText variant="title">hi there!</AppText>
    </Screen>
  );
}
