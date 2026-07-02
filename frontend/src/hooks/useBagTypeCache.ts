import { useCallback, useMemo, useState } from "react";
import type { BagType } from "../api/client";
import { fetchBagTypeById, fetchBagTypesByIds } from "../lib/masterSearch";

export function useBagTypeCache(initial: BagType[] = []) {
  const [cache, setCache] = useState<Map<number, BagType>>(() => {
    const map = new Map<number, BagType>();
    for (const bt of initial) map.set(bt.id, bt);
    return map;
  });

  const remember = useCallback((bt: BagType) => {
    setCache((prev) => {
      if (prev.get(bt.id) === bt) return prev;
      const next = new Map(prev);
      next.set(bt.id, bt);
      return next;
    });
  }, []);

  const rememberMany = useCallback((items: BagType[]) => {
    if (!items.length) return;
    setCache((prev) => {
      const next = new Map(prev);
      for (const bt of items) next.set(bt.id, bt);
      return next;
    });
  }, []);

  const get = useCallback(
    (id: number | string | null | undefined): BagType | undefined => {
      if (id == null || id === "") return undefined;
      return cache.get(Number(id));
    },
    [cache]
  );

  const ensure = useCallback(
    async (id: number | string | null | undefined): Promise<BagType | undefined> => {
      if (id == null || id === "") return undefined;
      const num = Number(id);
      const existing = cache.get(num);
      if (existing) return existing;
      const fetched = await fetchBagTypeById(num);
      if (fetched) remember(fetched);
      return fetched ?? undefined;
    },
    [cache, remember]
  );

  const ensureMany = useCallback(
    async (ids: Array<number | string | null | undefined>) => {
      const missing = [
        ...new Set(
          ids
            .filter((id) => id != null && id !== "")
            .map((id) => Number(id))
            .filter((id) => !cache.has(id))
        ),
      ];
      if (!missing.length) return;
      const fetched = await fetchBagTypesByIds(missing);
      rememberMany(fetched);
    },
    [cache, rememberMany]
  );

  const list = useMemo(() => [...cache.values()], [cache]);

  return { get, remember, rememberMany, ensure, ensureMany, list, cache };
}
