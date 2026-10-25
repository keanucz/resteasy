import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

import {
  CONNECT_STEP_MS,
  CONNECT_STEPS,
  DEMO_PILLOW_ID,
  LINK_STORAGE_PREFIX,
} from "@/constants/pillow";
import { api } from "@/services/api";

/** Someone this login looks after, from GET /me: their pillow, and whether the login owns it. */
export type Person = {
  pillow_id: string;
  resident_id: string;
  preferred_name: string;
  role: "owner" | "contact";
};

type PillowLink = {
  /** The connected pillow's id, or null before "Connect pillow". */
  pillowId: string | null;
  /** Everyone this login looks after (empty until /me answers, or for a fresh sign-up). */
  people: Person[];
  /** The signed-in family member's full name from /me, or null when unknown. */
  myName: string | null;
  /** True once /me has answered for this login, so routing can wait instead of flashing "Connect". */
  ready: boolean;
  /** Show another person's pillow; remembered on this device like the first link. */
  select: (pillowId: string) => void;
  /** Run the (mocked) pairing, calling `onStep` with each step's index; resolves once linked. */
  connect: (onStep: (step: number) => void) => Promise<void>;
  disconnect: () => void;
};

const PillowLinkContext = createContext<PillowLink | null>(null);

const NO_PEOPLE: Person[] = [];

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

type Account = { people: Person[]; myName: string | null };
type Me = { pillows: Person[]; full_name?: string | null };

/**
 * The first pillow this login is a contact for. A new sign-up looks after nobody yet, so it joins
 * the demo household first (POST /me/join-demo), or the backend and the database would refuse it.
 */
async function accountPillow(): Promise<string> {
  const account = await readAccount();
  const first = account.people[0] ?? (await joinDemo()).people[0];
  return first?.pillow_id ?? DEMO_PILLOW_ID;
}

function toAccount(me: Me): Account {
  return { people: me.pillows, myName: me.full_name ?? null };
}

/** Everyone the signed-in login looks after, and their own name; none on any error. */
async function readAccount(): Promise<Account> {
  try {
    return toAccount(await api<Me>("/me"));
  } catch {
    return { people: [], myName: null };
  }
}

/** Make this login a contact of the demo pillow's resident; the account after, or none on error. */
async function joinDemo(): Promise<Account> {
  try {
    return toAccount(await api<Me>("/me/join-demo", { method: "POST" }));
  } catch {
    return { people: [], myName: null };
  }
}

/** Read this device's saved link for a login; storage can be missing or blocked, so fail to "not linked". */
function readLink(userId: string): string | null {
  try {
    return (
      globalThis.localStorage?.getItem(LINK_STORAGE_PREFIX + userId) ?? null
    );
  } catch {
    return null;
  }
}

function writeLink(userId: string, pillowId: string | null) {
  try {
    if (pillowId)
      globalThis.localStorage?.setItem(LINK_STORAGE_PREFIX + userId, pillowId);
    else globalThis.localStorage?.removeItem(LINK_STORAGE_PREFIX + userId);
  } catch {
    // The link then lasts until the app closes, which is fine for a mock.
  }
}

/**
 * Which pillow this login has connected, remembered on this device. Pairing is a mock: it walks
 * through the steps and links the login's own pillow (or the demo one); real pairing replaces it later.
 */
export function PillowLinkProvider({
  userId,
  children,
}: PropsWithChildren<{ userId: string | null }>) {
  const [link, setLink] = useState(() => ({
    userId,
    pillowId: userId ? readLink(userId) : null,
  }));
  // A different login (or logging out) reads that login's own saved link, during render.
  if (link.userId !== userId)
    setLink({ userId, pillowId: userId ? readLink(userId) : null });
  const { pillowId } = link;
  // Whose list this is, so a different login never sees the last one's people while /me loads.
  const [found, setFound] = useState<{
    userId: string | null;
    people: Person[];
    myName: string | null;
  }>({
    userId: null,
    people: [],
    myName: null,
  });
  const ready = found.userId === userId;
  const people = ready ? found.people : NO_PEOPLE;
  const myName = ready ? found.myName : null;

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    // A login linked on this device before it joined anyone (an older sign-up) joins now.
    readAccount()
      .then((account) =>
        account.people.length === 0 && readLink(userId) ? joinDemo() : account,
      )
      .then((account) => {
        if (cancelled) return;
        setFound({ userId, ...account });
        // A login that already looks after someone opens straight onto their pillow, on any device or
        // fresh install, instead of walking through pairing again.
        const first = account.people[0]?.pillow_id;
        if (first && !readLink(userId)) {
          writeLink(userId, first);
          setLink({ userId, pillowId: first });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  const connect = useCallback(
    async (onStep: (step: number) => void) => {
      const found = accountPillow();
      for (let step = 0; step < CONNECT_STEPS.length; step++) {
        onStep(step);
        await wait(CONNECT_STEP_MS);
      }
      const pillowId = await found;
      if (userId) writeLink(userId, pillowId);
      setLink({ userId, pillowId });
    },
    [userId],
  );

  const disconnect = useCallback(() => {
    if (userId) writeLink(userId, null);
    setLink({ userId, pillowId: null });
  }, [userId]);

  const select = useCallback(
    (next: string) => {
      if (userId) writeLink(userId, next);
      setLink({ userId, pillowId: next });
    },
    [userId],
  );

  return (
    <PillowLinkContext.Provider
      value={{ pillowId, people, myName, ready, select, connect, disconnect }}
    >
      {children}
    </PillowLinkContext.Provider>
  );
}

export function usePillowLink(): PillowLink {
  const link = useContext(PillowLinkContext);
  if (!link) throw new Error("usePillowLink needs a PillowLinkProvider");
  return link;
}
