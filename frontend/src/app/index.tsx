import { useEffect, useState } from 'react';
import { Button } from 'react-native';

import { AppText } from '@/components/AppText';
import { Screen } from '@/components/Screen';
import { env } from '@/config/env';
import { testConnection } from '@/services/api/connection';

/** Call GET /api/test and describe the result in one line. */
function describeBackend(): Promise<string> {
  return testConnection().then(
    (result) => `${result.message} via ${result.host} at ${result.server_time}`,
    (error) => `unreachable: ${String(error)}`,
  );
}

/** Home route ("/"): calls the backend so you can see the app and API are wired up. */
export default function HomeScreen() {
  const [backendStatus, setBackendStatus] = useState('checking...');

  useEffect(() => {
    describeBackend().then(setBackendStatus);
  }, []);

  const checkAgain = () => {
    setBackendStatus('checking...');
    describeBackend().then(setBackendStatus);
  };

  return (
    <Screen>
      <AppText variant="title">Pillow</AppText>
      <AppText>API: {env.apiUrl}</AppText>
      <AppText>Backend: {backendStatus}</AppText>
      <Button title="Check again" onPress={checkAgain} />
    </Screen>
  );
}
