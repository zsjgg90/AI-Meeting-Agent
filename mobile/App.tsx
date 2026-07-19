import { StatusBar } from 'expo-status-bar';
import MeetingRecorderScreen from './src/screens/MeetingRecorderScreen';

export default function App() {
  return (
    <>
      <MeetingRecorderScreen />
      <StatusBar style="auto" />
    </>
  );
}
