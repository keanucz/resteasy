import { View } from 'react-native';

/** Shown for the moment after sign-in while /me says whether this login already has a pillow. */
export default function LoadingScreen() {
  return <View className="flex-1 bg-canvas" accessibilityLabel="Loading" />;
}
