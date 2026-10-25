import { Image, Modal, Pressable, Text, View } from 'react-native';

import { Avatar } from '@/components/Avatar';
import { List, ListRow } from '@/components/List';
import { ThemeRoot } from '@/components/ThemeRoot';
import { type Person, usePillowLink } from '@/hooks/usePillowLink';
import { useResidentPhoto } from '@/hooks/useResidentPhoto';

/** "Margaret" as "M". */
const initial = (name: string) => name.trim().charAt(0).toUpperCase() || '?';

/** Their photo if the household added one, else their initial. */
function PersonFace({ person }: { person: Person }) {
  const photo = useResidentPhoto(person.resident_id);
  return photo ? (
    <Image source={{ uri: photo }} accessible={false} className="size-11 rounded-full" />
  ) : (
    <Avatar initials={initial(person.preferred_name)} />
  );
}

/**
 * Everyone this login looks after, one row each. The one on screen says "Showing"; tapping another
 * switches the whole app to their pillow.
 */
export function PeopleList({ onPicked }: { onPicked?: () => void }) {
  const { people, pillowId, select } = usePillowLink();
  return (
    <List>
      {people.map((person) => {
        const showing = person.pillow_id === pillowId;
        return (
          <ListRow
            key={person.pillow_id}
            leading={<PersonFace person={person} />}
            title={person.preferred_name}
            meta={person.role === 'owner' ? 'You set up their pillow' : 'You are in their care circle'}
            trailing={showing ? <Text className="font-sans-semibold text-sm text-ink-muted">Showing</Text> : undefined}
            onPress={() => {
              if (!showing) select(person.pillow_id);
              onPicked?.();
            }}
          />
        );
      })}
    </List>
  );
}

/** The same list in a sheet, opened from the photo on Tonight. */
export function PeopleSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  return (
    <Modal transparent animationType="fade" visible={visible} onRequestClose={onClose}>
      {/* The modal renders outside the app root on web, so it needs its own theme variables. */}
      <ThemeRoot>
        <Pressable
          accessibilityLabel="Close"
          onPress={onClose}
          className="flex-1 items-center justify-center bg-black/50 p-6"
        >
          {/* Stops a tap inside the sheet from closing it. */}
          <Pressable className="w-full max-w-sm gap-3 rounded-card bg-canvas p-[18px]" onPress={() => {}}>
            <Text className="font-display text-lg text-ink">Who to show</Text>
            <View>
              <PeopleList onPicked={onClose} />
            </View>
          </Pressable>
        </Pressable>
      </ThemeRoot>
    </Modal>
  );
}
