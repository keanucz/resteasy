import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  CONNECT_FAILED,
  CONNECT_STEP_MS,
  CONNECT_STEPS,
  LINK_STORAGE_PREFIX,
  PILLOW_SILENT,
  PILLOW_TAKEN,
  SPEAKER_SILENT,
} from "@/constants/pillow";
import { api, ApiError } from "@/services/api";
import { type PillowPing, pingPillow } from "@/services/ping";

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
  /** Run the pairing, calling `onStep` with each step's index; resolves once linked, and rejects
   * with a message to show when the login couldn't be given a pillow or the pillow didn't answer.
   * With `name`, first sets the pillow up for that person (a login that looks after nobody yet). */
  connect: (onStep: (step: number) => void, name?: string) => Promise<void>;
  /** Read /me again and update `people`; null when the backend can't be reached, so a failed read is
   * never mistaken for a login that looks after nobody. */
  refreshAccount: () => Promise<Account | null>;
  disconnect: () => void;
};

const PillowLinkContext = createContext<PillowLink | null>(null);

const NO_PEOPLE: Person[] = [];

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

type Account = { people: Person[]; myName: string | null };
type Me = { pillows: Person[]; full_name?: string | null };

/**
 * The login's account with the first pillow it looks after. Throws when there's none: linking a
 * pillow the login isn't a contact of would leave every screen refused by the backend and the database.
 */
async function accountPillow(): Promise<Account> {
  const account = await readAccount();
  if (!account?.people[0]) throw new Error(CONNECT_FAILED);
  return account;
}

/** Set the pillow up for `name`, with this login as their owner (POST /me/pillows); the account after. */
async function createPillow(name: string): Promise<Account> {
  try {
    return toAccount(await api<Me>("/me/pillows", { method: "POST", body: { name } }));
  } catch (e) {
    throw new Error(e instanceof ApiError && e.status === 409 ? PILLOW_TAKEN : CONNECT_FAILED);
  }
}

/** Ping the pillow and throw a message to show unless both its boards answered. */
async function requireBothBoards(pillowId: string): Promise<void> {
  let ping: PillowPing;
  try {
    ping = await pingPillow(pillowId);
  } catch {
    throw new Error(CONNECT_FAILED);
  }
  if (!ping.active) throw new Error(ping.node_alive ? SPEAKER_SILENT : PILLOW_SILENT);
}

function toAccount(me: Me): Account {
  return { people: me.pillows, myName: me.full_name ?? null };
}

/** Everyone the signed-in login looks after, and their own name; null when /me can't be read. */
async function readAccount(): Promise<Account | null> {
  try {
    return toAccount(await api<Me>("/me"));
  } catch {
    return null;
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
 * Which pillow this login has connected, remembered on this device. Pairing links the login's own
 * pillow, or sets the pillow up for the person a new login names, then pings it before linking.
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
    readAccount()
      .then((account) => {
        if (cancelled) return;
        // Unreachable backend: keep this device's link, so a known login still opens its pillow.
        if (!account) {
          setFound({ userId, people: [], myName: null });
          return;
        }
        setFound({ userId, ...account });
        // A login that already looks after someone opens straight onto their pillow, on any device or
        // fresh install, instead of walking through pairing again. A saved link to a pillow the
        // login doesn't look after (left by an older pairing that fell back to the demo pillow) is
        // replaced, or dropped so the login pairs again.
        const saved = readLink(userId);
        const first = account.people[0]?.pillow_id ?? null;
        if (!account.people.some((p) => p.pillow_id === saved) && saved !== first) {
          writeLink(userId, first);
          setLink({ userId, pillowId: first });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  // The pairing in progress: a second tap (or the name screen's return key) joins it, so the pillow
  // is never set up twice.
  const pairing = useRef<Promise<void> | null>(null);

  const pair = useCallback(
    async (onStep: (step: number) => void, name?: string) => {
      // A retry after the pillow was set up but didn't answer the ping links it, never sets it up again
      const found = name === undefined || people.length > 0 ? accountPillow() : createPillow(name);
      // Ping as soon as the pillow is known, while the steps play
      const answered = found.then((account) => requireBothBoards(account.people[0].pillow_id));
      // Handled by the awaits below; this only stops an early failure being reported as unhandled.
      answered.catch(() => {});
      for (let step = 0; step < CONNECT_STEPS.length; step++) {
        onStep(step);
        await wait(CONNECT_STEP_MS);
      }
      const account = await found;
      // A newly set-up pillow shows in the people list straight away, not after the next /me
      if (userId) setFound({ userId, ...account });
      await answered;
      const pillowId = account.people[0].pillow_id;
      if (userId) writeLink(userId, pillowId);
      setLink({ userId, pillowId });
    },
    [userId, people],
  );

  const connect = useCallback(
    (onStep: (step: number) => void, name?: string) => {
      if (!pairing.current) {
        pairing.current = pair(onStep, name).finally(() => {
          pairing.current = null;
        });
      }
      return pairing.current;
    },
    [pair],
  );

  const refreshAccount = useCallback(async () => {
    const account = await readAccount();
    if (account && userId) setFound({ userId, ...account });
    return account;
  }, [userId]);

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

  // The same object until something in it changes, so screens re-render only when it does.
  const value = useMemo(
    () => ({ pillowId, people, myName, ready, select, connect, refreshAccount, disconnect }),
    [pillowId, people, myName, ready, select, connect, refreshAccount, disconnect],
  );
  return <PillowLinkContext.Provider value={value}>{children}</PillowLinkContext.Provider>;
}

export function usePillowLink(): PillowLink {
  const link = useContext(PillowLinkContext);
  if (!link) throw new Error("usePillowLink needs a PillowLinkProvider");
  return link;
}
