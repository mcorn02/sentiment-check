import { useState, useEffect } from 'react';
import type { DomainConfig } from '../types/report';

export function useDomains() {
  const [domains, setDomains] = useState<DomainConfig[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetch('/api/domains')
      .then(res => res.json())
      .then(data => setDomains(data))
      .catch(() => setDomains([]))
      .finally(() => setIsLoading(false));
  }, []);

  return { domains, isLoading };
}
